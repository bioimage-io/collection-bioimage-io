import json
import os
import warnings
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import DefaultDict, Dict, List, Literal, Optional, Sequence, Union

import requests
import typer
from github import Github
from ruamel.yaml import YAML

yaml = YAML(typ="safe")


def set_gh_actions_output(name: str, output: str):
    """set output of a github actions workflow step calling this script"""
    # escape special characters when setting github actions step output
    output = output.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::set-output name={name}::{output}")


def get_rdf_source(*, rdf_urls: List[str], doi, concept_doi) -> dict:
    if len(rdf_urls) == 1:
        r = requests.get(rdf_urls[0])
        if r.status_code != 200:
            warnings.warn(
                f"Could not get rdf.yaml for new version {doi} of {concept_doi} ({r.status_code}: {r.reason}); "
                "skipping update"
            )
            rdf = {}
        else:
            rdf = yaml.load(r.text)
            if not isinstance(rdf, dict):
                warnings.warn(
                    f"Found invalid rdf.yaml (not a dict) for new version {doi} of {concept_doi}; "
                    "writing empty rdf.yaml"
                )
                rdf = {}
    else:
        warnings.warn(
            f"Found {len(rdf_urls)} rdf.yaml files for new version {doi} of {concept_doi}; " "writing empty rdf.yaml"
        )
        rdf = {}

    return rdf


def write_resource(
    *,
    resource_path: Path,
    resource_id: str,
    resource_doi: Optional[str],
    version_id: str,
    new_version: dict,
    overwrite: bool = False,
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
            if known_version["version_id"] == version_id:
                if overwrite:
                    old_version = resource["versions"].pop(idx)
                    if old_version != new_version:
                        break

                # fetched resource is known
                return "old_hit"

        # extend resource by new version
        resource["versions"].insert(0, new_version)
        # make sure latest is first
        resource["versions"].sort(key=lambda v: v["created"], reverse=True)
    else:  # create new resource
        resource = {
            "status": "pending",
            "versions": [new_version],
            "resource_id": resource_id,
            "resource_doi": resource_doi,
        }

    assert isinstance(resource, dict)
    resource_path.parent.mkdir(parents=True, exist_ok=True)
    yaml.dump(resource, resource_path)
    return resource


def update_with_new_version(
    new_version: dict, resource_id: str, rdf: Optional[dict], updated_resources: DefaultDict[str, List[Dict[str, str]]]
):
    # add more fields just
    maintainers = []
    if rdf is not None:
        _maintainers = rdf.get("maintainers")
        if isinstance(_maintainers, list) and all(isinstance(m, dict) for m in _maintainers):
            maintainers = [m.get("github_user") for m in _maintainers]
            # only expect non empty strings and prepend single '@'
            maintainers = ["@" + m.strip("@") for m in maintainers if isinstance(m, str) and m]

    new_version["maintainers"] = maintainers
    updated_resources[resource_id].append(new_version)


def update_from_zenodo(collection_folder: Path, updated_resources: DefaultDict[str, List[Dict[str, str]]]):
    for page in range(1, 10):
        zenodo_request = f"https://zenodo.org/api/records/?&sort=mostrecent&page={page}&size=1000&all_versions=1&keywords=bioimage.io"
        print(zenodo_request)
        r = requests.get(zenodo_request)
        if not r.status_code == 200:
            warnings.warn(f"Could not get zenodo records page {page}: {r.status_code}: {r.reason}")
            break

        hits = r.json()["hits"]["hits"]
        if not hits:
            break

        for hit in hits:
            resource_doi = hit["conceptdoi"]
            doi = hit["doi"]  # "version" doi
            created = hit["created"]
            resource_path = collection_folder / resource_doi / "resource.yaml"
            version_name = f"revision {hit['revision']}"
            rdf_urls = [file_hit["links"]["self"] for file_hit in hit["files"] if file_hit["key"] == "rdf.yaml"]
            rdf = None
            source = "unknown"
            name = doi
            if len(rdf_urls) > 0:
                if len(rdf_urls) > 1:
                    warnings.warn("found multiple 'rdf.yaml' sources?!?")

                source = sorted(rdf_urls)[0]
                try:
                    r = requests.get(source)
                    rdf = yaml.load(r.text)
                    name = rdf.get("name", doi)
                except Exception as e:
                    warnings.warn(f"Failed to obtain version name: {e}")

            new_version = {
                "version_id": doi,
                "doi": doi,
                "created": created,
                "status": "pending",
                "source": source,
                "name": name,
                "version_name": version_name,
            }
            resource = write_resource(
                resource_path=resource_path,
                resource_id=resource_doi,
                resource_doi=resource_doi,
                version_id=doi,
                new_version=new_version,
            )
            if resource not in ("blocked", "old_hit"):
                assert isinstance(resource, dict)
                update_with_new_version(new_version, resource_doi, rdf, updated_resources)


def update_from_collection(
    collection_folder: Path,
    collection_id: str,
    collection_source: str,
    updated_resources: DefaultDict[str, List[Dict[str, str]]],
    resource_types: Sequence[str],
    gh: Github,
):
    req = requests.get(collection_source)
    if not req.status_code == 200:
        raise RuntimeError(f"Could not get collection from {collection_source}: {req.status_code}: {req.reason}")

    c = yaml.load(req.text)
    for rtype in resource_types:
        for r in c.get(rtype, []):
            try:
                collection_item = {k: v for k, v in r.items() if k != "id"}
                source = r["source"]
                resource_id = f"{collection_id}/{r['id']}"
                # no version_id for rdfs only specified in the collection (not in separate rdf under source)
                version_id = resource_id
                version_name = "latest"
                created = datetime.fromordinal(1)

                # assume rdf is defined outside of collection under source (that also lives in github)
                rdf = None
                githubusercontent_url = "https://raw.githubusercontent.com/"
                if source.startswith(githubusercontent_url) and source.endswith(".yaml"):
                    try:
                        req = requests.get(source)
                        rdf = yaml.load(req.text)
                        if not isinstance(rdf, dict):
                            raise TypeError(f"rdf type: type(rdf)")

                    except Exception as e:
                        warnings.warn(f"Failed to load rdf from {source}: {e}")
                        rdf = None
                    else:
                        try:
                            orga, repo, branch, *_ = source[len(githubusercontent_url) :].split("/")
                            repo = gh.get_repo(f"{orga}/{repo}")
                            commit = repo.get_commit(branch)
                            tag = repo.get_git_tag(commit.sha)
                        except Exception as e:
                            warnings.warn(f"Failed to fetch version_id from github: {e}")
                        else:
                            version_id = tag.sha
                            version_name = tag.tag

                # fallback assumes rdf is defined in collection; source does not point to a (valid) rdf
                if rdf is None:
                    rdf = {}
                    source = collection_item
                    new_version = {}
                else:
                    # collection item specifies update rdf, like we allow for a manual update here
                    new_version = collection_item

                new_version.update(
                    {
                        "version_id": version_id,
                        "created": created,
                        "status": "pending",
                        "source": source,
                        "name": rdf.get("name", resource_id),
                        "version_name": version_name,
                    }
                )

                resource = write_resource(
                    resource_path=collection_folder / resource_id / "resource.yaml",
                    resource_id=resource_id,
                    resource_doi=None,
                    version_id=version_id,
                    new_version=new_version,
                    overwrite=True,
                )
                if resource not in ("blocked", "old_hit"):
                    assert isinstance(resource, dict)
                    update_with_new_version(new_version, resource_id, rdf, updated_resources)

            except Exception as e:
                # don't fail for single bad resource in collection
                warnings.warn(f"Failed to add resource: {e}")


def update_from_github(collection_folder: Path, updated_resources: DefaultDict[str, List[Dict[str, str]]]):
    rdf_template = yaml.load(collection_folder.parent / "collection_rdf_template.yaml")
    partners = rdf_template["config"]["partners"]
    resource_types = rdf_template["config"]["resource_types"]
    gh = Github()

    for p in partners:
        p_id = "unknown"
        p_source = "unknown"
        try:
            p_id = p["id"]
            p_source = p["source"]
            update_from_collection(collection_folder, p_id, p_source, updated_resources, resource_types, gh)
        except Exception as e:
            warnings.warn(f"Failed to process collection {p_source} for {p_id} partner: {e}")


def main(collection_folder: Path) -> int:
    updated_resources: DefaultDict[str, List[Dict[str, str]]] = defaultdict(list)

    update_from_zenodo(collection_folder, updated_resources)
    update_from_github(collection_folder, updated_resources)

    set_gh_actions_output(
        "updated_resources_matrix",
        json.dumps(
            {
                "update": [
                    {
                        "resource_id": k,
                        "new_version_ids": json.dumps([vv["version_id"] for vv in v]),
                        "new_version_ids_md": "\n".join(["  - " + vv["version_id"] for vv in v]),
                        "new_version_sources": json.dumps([vv["source"] for vv in v]),
                        "new_version_sources_md": "\n".join(["  - " + vv["source"] for vv in v]),
                        "resource_name": v[0]["name"],
                        "maintainers": str(list(set(sum((vv["maintainers"] for vv in v), start=[]))))[1:-1].replace(
                            "'", ""
                        )
                        or "none specified",
                    }
                    for k, v in updated_resources.items()
                ]
            }
        ),
    )
    set_gh_actions_output("found_new_resources", "yes" if updated_resources else "")

    return 0


if __name__ == "__main__":
    typer.run(main)
