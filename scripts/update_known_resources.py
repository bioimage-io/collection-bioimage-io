import json
import subprocess
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from pprint import pprint
from typing import DefaultDict, Dict, List, Literal, Optional, Tuple, Union

import requests
import typer
from ruamel.yaml import YAML

from utils import set_gh_actions_output

yaml = YAML(typ="safe")


def get_rdf_source(*, rdf_urls: List[str], doi, concept_doi) -> dict:
    if len(rdf_urls) == 1:
        r = requests.get(rdf_urls[0])
        if r.status_code != 200:
            print(
                f"Could not get rdf.yaml for new version {doi} of {concept_doi} ({r.status_code}: {r.reason}); "
                "skipping update"
            )
            rdf = {}
        else:
            rdf = yaml.load(r.text)
            if not isinstance(rdf, dict):
                print(
                    f"Found invalid rdf.yaml (not a dict) for new version {doi} of {concept_doi}; "
                    "writing empty rdf.yaml"
                )
                rdf = {}
    else:
        print(f"Found {len(rdf_urls)} rdf.yaml files for new version {doi} of {concept_doi}; " "writing empty rdf.yaml")
        rdf = {}

    return rdf


def write_resource(
    *,
    resource_path: Path,
    resource_id: str,
    resource_type: str,
    resource_doi: Optional[str],
    version_id: str,
    new_version: dict,
) -> Union[dict, Literal["old_hit", "blocked"]]:
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
            if known_version["version_id"] == version_id or new_version.get("source") == known_version.get("source"):
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

    if "doi" in resource and not resource["doi"]:
        del resource["doi"]

    assert isinstance(resource, dict)
    resource_path.parent.mkdir(parents=True, exist_ok=True)
    yaml.dump(resource, resource_path)
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
    collection_dir: Path, updated_resources: DefaultDict[str, List[Dict[str, Union[str, datetime]]]]
):
    for page in range(1, 10):
        zenodo_request = f"https://zenodo.org/api/records/?&sort=mostrecent&page={page}&size=1000&all_versions=1&keywords=bioimage.io"
        r = requests.get(zenodo_request)
        if not r.status_code == 200:
            print(f"Could not get zenodo records page {page}: {r.status_code}: {r.reason}")
            break
        print(f"Collecting items from zenodo: {zenodo_request}")

        hits = r.json()["hits"]["hits"]
        if not hits:
            break

        for hit in hits:
            resource_doi = hit["conceptdoi"]
            doi = hit["doi"]  # "version" doi
            created = datetime.fromisoformat(hit["created"]).replace(tzinfo=None)
            assert isinstance(created, datetime), created
            resource_path = collection_dir / resource_doi / "resource.yaml"
            version_name = f"revision {hit['revision']}"
            rdf_urls = [file_hit["links"]["self"] for file_hit in hit["files"] if file_hit["key"] == "rdf.yaml"]
            rdf = None
            source = "unknown"
            name = doi
            resource_type = "unknown"
            if len(rdf_urls) > 0:
                if len(rdf_urls) > 1:
                    print("found multiple 'rdf.yaml' sources?!?")

                source = sorted(rdf_urls)[0]
                try:
                    r = requests.get(source)
                    rdf = yaml.load(r.text)
                    name = rdf.get("name", doi)
                    resource_type = rdf.get("type")
                except Exception as e:
                    print(f"Failed to obtain version name: {e}")

            new_version = {
                "version_id": doi,
                "doi": doi,
                "created": created,
                "status": "accepted",  # default to accepted
                "source": source,
                "name": name,
                "version_name": version_name,
            }
            resource = write_resource(
                resource_path=resource_path,
                resource_id=resource_doi,
                resource_type=resource_type,
                resource_doi=resource_doi,
                version_id=doi,
                new_version=new_version,
            )
            if resource not in ("blocked", "old_hit"):
                assert isinstance(resource, dict)
                update_with_new_version(new_version, resource_doi, rdf, updated_resources)


def main(collection_dir: Path, max_resource_count: int) -> int:
    updated_resources: DefaultDict[str, List[Dict[str, Union[str, datetime]]]] = defaultdict(list)

    update_from_zenodo(collection_dir, updated_resources)

    # limit the number of PRs created
    oldest_updated_resources: List[Tuple[str, List[Dict[str, str]]]] = sorted(  # type: ignore
        updated_resources.items(), key=lambda kv: (min([vv["created"] for vv in kv[1]]), kv[0])
    )
    limited_updated_resources = dict(oldest_updated_resources[:max_resource_count])

    # remove pending resources (resources for which an auto-update-<resource_id> branch already exists)
    subprocess.run(["git", "fetch"])
    remote_branch_proc = subprocess.run(["git", "branch", "-r"], capture_output=True, text=True)
    remote_branches = [rb for rb in remote_branch_proc.stdout.split() if rb.startswith("origin/auto-update-")]
    print("Found remote auto-update branches:")
    pprint(remote_branches)
    limited_updated_resources = {
        k: v for k, v in limited_updated_resources.items() if f"origin/auto-update-{k}" not in remote_branches
    }

    updates = [
        {
            "resource_id": k,
            "new_version_ids": json.dumps([vv["version_id"] for vv in v]),
            "new_version_ids_md": "\n".join(["  - " + vv["version_id"] for vv in v]),
            "new_version_sources": json.dumps([(vv.get("source") or None) for vv in v]),
            "new_version_sources_md": "\n".join(
                [
                    "  - "
                    + (
                        f"dict(name={vv['source'].get('name')}, ...)"
                        if isinstance(vv["source"], dict)
                        else vv["source"]
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
    updated_resources_matrix = {"update": updates}
    print("updated_resources_matrix:")
    pprint(updated_resources_matrix)
    set_gh_actions_output("updated_resources_matrix", updated_resources_matrix)
    set_gh_actions_output("found_new_resources", "yes" if limited_updated_resources else "")

    return 0


if __name__ == "__main__":
    typer.run(main)
