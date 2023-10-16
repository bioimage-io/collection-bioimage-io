import json
import subprocess
import warnings
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from pprint import pprint
from typing import DefaultDict, Dict, List, Literal, Optional, Tuple, Union

import requests
import typer
from bare_utils import set_gh_actions_outputs
from utils import ADJECTIVES, ANIMALS, enforce_block_style_resource, get_animal_nickname, split_animal_nickname, yaml


def update_resource(
    *,
    resource_path: Path,
    resource_id: str,
    resource_type: str,
    resource_doi: Optional[str],
    version_id: str,
    new_version: dict,
    resource_output_path: Path,
    rdf: dict,
) -> Union[dict, Literal["old_hit", "blocked"]]:
    if resource_output_path.exists():
        # maybe we have more than one new versions, so we should update the resource that is already written to output
        resource_path = resource_output_path

    if resource_path.exists():
        resource = yaml.load(resource_path)
        assert isinstance(resource, dict)
        if resource["status"] == "blocked":
            return "blocked"
        elif resource["status"] in ("accepted", "pending"):
            assert resource[
                "versions"
            ], f"expected at least one existing version for {resource['status']} resource {resource_id}"
        else:
            raise ValueError(resource["status"])

        for idx, known_version in enumerate(list(resource["versions"])):
            if known_version["version_id"] == version_id and new_version.get("rdf_source") == known_version.get(
                "rdf_source"
            ):
                # fetched resource is known
                return "old_hit"

        # extend resource by new version
        resource["versions"].insert(0, new_version)
        # make sure latest is first
        resource["versions"].sort(key=lambda v: v["created"], reverse=True)
        resource["type"] = resource_type
    else:  # create new resource
        resource = {
            "status": "accepted",  # default to accepted
            "versions": [new_version],
            "id": resource_id,
            "doi": resource_doi,
            "type": resource_type,
        }

        # check/set nickname and nickname_icon
        def get_config_bioimageio(key):
            try:
                return rdf.get("config", {}).get("bioimageio", {}).get(key)
            except Exception as e:
                warnings.warn(f"Failed to get existing {key}: {e}")
                return None

        existing_nickname = get_config_bioimageio("nickname")
        existing_nickname_icon = get_config_bioimageio("nickname_icon")

        nickname = None
        nickname_icon = None
        if resource_type == "model":
            if existing_nickname is None:
                # suggest nickname and nickname_icon if missing (maybe we overwrite nickname_icon)
                nickname, nickname_icon = get_animal_nickname()
            else:
                try:
                    adjective, animal = split_animal_nickname(existing_nickname)
                    assert adjective in ADJECTIVES
                    assert animal in ANIMALS
                except Exception as e:
                    print("error", e)
                    # suggest to overwrite nickname and nickname_icon if nickname is invalid
                    nickname, nickname_icon = get_animal_nickname()
                else:
                    nickname = existing_nickname
                    nickname_icon = ANIMALS[animal]  # maybe we overwrite nickname_icon; it needs to match animal
        else:
            # set invalid nickname if any nickname was specified for a non-model resource
            if existing_nickname is not None:
                nickname = "nickname not allowed for for non model resources"

            # set invalid nickname_icon if any nickname_icon was specified for a non-model resource
            if existing_nickname_icon is not None:
                nickname_icon = "nickname_icon not allowed for for non model resources"

        # set nickname(_icon) even if present in rdf to make sure it will stay the same for future versions
        if nickname is not None:
            resource["nickname"] = nickname

        if nickname_icon is not None:
            resource["nickname_icon"] = nickname_icon

    if "owners" in new_version:
        resource["owners"] = new_version["owners"]
        del new_version["owners"]

    if "doi" in resource and not resource["doi"]:
        del resource["doi"]

    assert isinstance(resource, dict)
    resource_output_path.parent.mkdir(parents=True, exist_ok=True)
    yaml.dump(enforce_block_style_resource(resource), resource_output_path)
    return resource


def update_with_new_version(
    new_version: dict,
    resource_id: str,
    rdf: Optional[dict],
    updated_resources: DefaultDict[str, List[Dict[str, Union[str, datetime]]]],
):
    # add more fields just
    maintainers = []
    if isinstance(rdf, dict):
        _maintainers = rdf.get("maintainers")
        if isinstance(_maintainers, list) and all(isinstance(m, dict) for m in _maintainers):
            maintainers = [m.get("github_user") for m in _maintainers]
            # only expect non empty strings and prepend single '@'
            maintainers = ["@" + m.strip("@") for m in maintainers if isinstance(m, str) and m]

    new_version["maintainers"] = maintainers
    updated_resources[resource_id].append(new_version)


def update_from_zenodo(
    collection: Path,
    dist: Path,
    updated_resources: DefaultDict[str, List[Dict[str, Union[str, datetime]]]],
    ignore_status_5xx: bool,
):
    download_counts: Dict[str, int] = {}
    for page in range(1, 1000):
        zenodo_request = (
            f"https://zenodo.org/api/records?&sort=newest&page={page}&size=1000&all_versions=1&q=keywords:bioimage.io"
        )
        r = requests.get(zenodo_request)
        if not r.status_code == 200:
            print(f"Could not get zenodo records page {page}: {r.status_code}: {r.reason}")
            break

        print(f"Collecting items from zenodo: {zenodo_request}")

        hits = r.json()  #  ["hits"]["hits"]
        if not hits:
            break

        for hit in hits:
            resource_doi: str = hit["conceptdoi"]
            doi: str = hit["doi"]  # "version" doi
            created = datetime.fromisoformat(hit["created"]).replace(tzinfo=None)
            assert isinstance(created, datetime), created
            resource_path = collection / resource_doi / "resource.yaml"
            resource_output_path = dist / resource_doi / "resource.yaml"
            version_name = f"version from {hit['metadata']['publication_date']}"
            rdf_urls = [
                f"https://zenodo.org/api/records/{hit['record_id']}/files/{file_hit['filename']}/content"
                for file_hit in hit["files"]
                if (file_hit["filename"] == "rdf.yaml" or file_hit["filename"].endswith("bioimageio.yaml"))
            ]
            rdf = {}
            rdf_source = "unknown"
            name = doi
            resource_type = "unknown"
            if len(rdf_urls) > 0:
                if len(rdf_urls) > 1:
                    print("found multiple 'rdf.yaml' sources?!?")

                rdf_source = sorted(rdf_urls)[0]
                r = requests.get(rdf_source)
                try:
                    r.raise_for_status()
                except Exception as e:
                    print(f"Failed to download rdf: {e}")
                    if ignore_status_5xx and r.status_code // 100 == 5:
                        continue
                else:
                    try:
                        rdf = yaml.load(r.text)
                        assert isinstance(rdf, dict)
                    except Exception as e:
                        print(f"invalid rdf at {rdf_source} ({e})")
                        rdf = {}
                    else:
                        name = rdf.get("name", doi)
                        resource_type = rdf.get("type")

            try:
                download_count = int(hit["stats"]["unique_downloads"])  # todo: update zenodo api
            except Exception as e:
                warnings.warn(f"Could not determine download count: {e}")
                download_count = 1

            download_counts[resource_doi] = download_count
            version_id = str(hit["id"])

            new_version = {
                "version_id": version_id,
                "doi": doi,
                "owners": [hit["owner"]],
                "created": str(created),
                "status": "accepted",  # default to accepted
                "rdf_source": rdf_source,
                "name": name,
                "version_name": version_name,
            }
            resource = update_resource(
                resource_path=resource_path,
                resource_id=resource_doi,
                resource_type=resource_type,
                resource_doi=resource_doi,
                version_id=version_id,
                new_version=new_version,
                resource_output_path=resource_output_path,
                rdf=rdf,
            )
            if resource not in ("blocked", "old_hit"):
                assert isinstance(resource, dict)
                update_with_new_version(new_version, resource_doi, rdf, updated_resources)

    with Path("download_counts_offsets.json").open() as f:
        download_counts_offsets = json.load(f)

    download_counts = {k: v + download_counts_offsets.get(k, 0) for k, v in download_counts.items()}

    dist.mkdir(parents=True, exist_ok=True)
    with (dist / "download_counts.json").open("w", encoding="utf-8") as f:
        json.dump(download_counts, f, indent=2, sort_keys=True)


def main(
    collection: Path = Path(__file__).parent / "../collection",
    dist: Path = Path(__file__).parent / "../dist",
    max_resource_count: int = 3,
    ignore_status_5xx: bool = False,
):
    updated_resources: DefaultDict[str, List[Dict[str, Union[str, datetime]]]] = defaultdict(list)
    update_from_zenodo(collection, dist, updated_resources, ignore_status_5xx)

    # limit the number of PRs created
    oldest_updated_resources: List[Tuple[str, List[Dict[str, str]]]] = sorted(  # type: ignore
        updated_resources.items(), key=lambda kv: (min([vv["created"] for vv in kv[1]]), kv[0])
    )
    print(f"{len(oldest_updated_resources)} resources to update:")
    pprint(list(map(lambda kv: kv[0], oldest_updated_resources)))
    limited_updated_resources = dict(oldest_updated_resources[:max_resource_count])
    print(f"limited to max {max_resource_count} of resources with auto-update branches (starting with oldest):")
    pprint(list(limited_updated_resources.keys()))

    # remove pending resources (resources for which an auto-update-<resource_id> branch already exists)
    subprocess.run(["git", "fetch"])
    remote_branch_proc = subprocess.run(["git", "branch", "-r"], capture_output=True, text=True)
    remote_branches = [rb for rb in remote_branch_proc.stdout.split() if rb.startswith("origin/auto-update-")]
    print("Found existing auto-update branches:")
    pprint(remote_branches)
    limited_updated_resources = {
        k: v for k, v in limited_updated_resources.items() if f"origin/auto-update-{k}" not in remote_branches
    }
    print("Resources to open a new PR for:")
    pprint(list(limited_updated_resources.keys()))

    updates = [
        {
            "resource_id": k,
            "new_version_ids": json.dumps([vv["version_id"] for vv in v]),
            "new_version_ids_md": "\n".join(
                [f"  - [{vv['version_id']} ({vv['version_name']})](https://www.doi.org/{vv['doi']})" for vv in v]
            ),
            "new_version_sources": json.dumps([(vv.get("rdf_source") or None) for vv in v]),
            "new_version_sources_md": "\n".join(
                [
                    "  - "
                    + (
                        f"dict(name={vv['rdf_source'].get('name')}, ...)"
                        if isinstance(vv["rdf_source"], dict)
                        else vv["rdf_source"]
                    )
                    for vv in v
                ]
            ),
            "resource_name": v[0]["name"],
            "maintainers": str(list(set(sum((vv["maintainers"] for vv in v), start=[]))))[1:-1].replace("'", "")
            or "none specified",
        }
        for k, v in limited_updated_resources.items()
    ]

    output = dict(updated_resources_matrix={"update": updates}, found_new_resources=bool(limited_updated_resources))
    set_gh_actions_outputs(output)
    return output


if __name__ == "__main__":
    typer.run(main)
