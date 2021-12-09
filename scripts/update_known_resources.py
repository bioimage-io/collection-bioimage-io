import json
import sys
import warnings
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Literal, Optional, Sequence, Tuple, Union

import requests
import typer
from ruamel.yaml import YAML

import bioimageio.spec.model.schema
from bioimageio.spec.shared.raw_nodes import URI

yaml = YAML(typ="safe")


def set_gh_actions_output(name: str, output: str):
    """set output of a github actions workflow step calling this script"""
    # escape special characters when setting github actions step output
    output = output.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::set-output name={name}::{output}")


def write_concept(
    *, concept_path: Path, id_: str, concept_doi: Optional[str], version_id: str, new_version: dict
) -> Union[dict, Literal["old_hit", "blocked"]]:
    if concept_path.exists():
        concept = yaml.load(concept_path)
        assert isinstance(concept, dict)
        if concept["status"] == "blocked":
            return "blocked"
        elif concept["status"] in ("accepted", "pending"):
            assert concept["versions"], f"expected at least one existing version for {concept['status']} concept {id_}"
        else:
            raise ValueError(concept["status"])

        for known_version in concept["versions"]:
            if known_version["version_id"] == version_id:
                # fetched resource is known; assume all following older resources have been processed earlier
                return "old_hit"

        # extend concept by new version
        concept["pending_versions"].append(new_version)
    else:  # create new concept
        concept = {"status": "pending", "versions": [new_version], "id": id_, "concept_doi": concept_doi}

    assert isinstance(concept, dict)
    concept_path.parent.mkdir(parents=True, exist_ok=True)
    yaml.dump(concept, concept_path)
    return concept


def get_rdf(*, rdf_urls: List[str], doi, concept_doi) -> dict:
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
        source = None
    return rdf


def write_conda_env_file(
    type_: Literal["rdf", "model"], rdf: dict, weight_format: str, file_hits: Sequence[dict], path: Path
):
    # minimal env for invalid model rdf to be checked with bioimageio.spec for validation errors only
    conda_env = {"channels": ["conda-forge", "defaults"], "dependencies": ["bioimageio.spec"]}
    if type_ == "rdf":
        pass
    elif type_ == "model":
        if weight_format:
            weights = rdf["weights"][weight_format]
            if weight_format in ["pytorch_state_dict"]:  # weights with specified dependencies field
                dep_data = weights.get("dependencies")  # model spec > 0.4.0
                if not dep_data:
                    dep_data = rdf.get("dependencies")  # model spec <= 0.4.0

                if dep_data:
                    try:
                        dep_node = bioimageio.spec.shared.fields.Dependencies().deserialize(dep_data)
                        if dep_node.manager in ["conda", "pip"]:
                            if isinstance(dep_node.file, Path):
                                # look for file name in file_hits
                                dep_file_urls = [
                                    file_hit["links"]["self"]
                                    for file_hit in file_hits
                                    if file_hit["key"] == dep_node.file.name
                                ]
                                if len(dep_file_urls) != 1:
                                    raise ValueError(f"Could not get url of dependency file {dep_node.file}")

                                dep_file_url = dep_file_urls[0]
                            elif isinstance(dep_node.file, URI):
                                dep_file_url = str(dep_node.file)
                            else:
                                raise TypeError(dep_node.file)

                            r = requests.get(dep_file_url)
                            r.raise_for_status()
                            dep_file_content = r.text
                            if dep_node.manager == "conda":
                                conda_env = yaml.load(dep_file_content)
                                # add bioimageio.core if not present
                                channels = conda_env.get("channels", [])
                                if "conda-forge" not in channels:
                                    conda_env["channels"] = channels + ["conda-forge"]

                                deps = conda_env.get("dependencies", [])
                                if not isinstance(deps, list):
                                    raise TypeError(
                                        f"expected dependencies in conda environment.yaml to be a list, but got: {deps}"
                                    )
                                if not any(d.startswith("bioimageio.core") for d in deps):
                                    conda_env["dependencies"] = deps + ["bioimageio.core"]
                            elif dep_node.manager == "pip":
                                pip_req = [d for d in dep_file_content.split("\n") if not d.strip().startswith("#")]
                                conda_env["dependencies"].append("bioimageio.core")
                                conda_env["dependencies"].append("pip")
                                conda_env["dependencies"].append({"pip": pip_req})  # type: ignore
                            else:
                                raise NotImplementedError(dep_node.manager)

                    except Exception as e:
                        warnings.warn(f"Failed to resolve weight dependencies: {e}")

            elif weight_format == "torchscript":
                conda_env["dependencies"].append("bioimageio.core")
                conda_env["channels"].insert(0, "pytorch")
                conda_env["dependencies"].append("pytorch")
                conda_env["dependencies"].append("cpuonly")
                # todo: pin pytorch version for torchscript (add version to torchscript weight spec)
            elif weight_format == "tensorflow_saved_model_bundle":
                conda_env["dependencies"].append("bioimageio.core")
                tf_version = weights.get("tensorflow_version")
                if not tf_version:
                    # todo: document default tf version
                    tf_version = "1.15"
                conda_env["dependencies"].append(f"tensorflow={tf_version}")
            elif weight_format == "onnx":
                conda_env["dependencies"].append("bioimageio.core")
                conda_env["dependencies"].append("onnxruntime")
                # note: we should not need to worry about the opset version,
                # see https://github.com/microsoft/onnxruntime/blob/master/docs/Versioning.md
            else:
                warnings.warn(f"Unknown weight format '{weight_format}'")
                # todo: add weight formats

    else:
        ValueError(type_)

    conda_env["name"] = "validation"

    path.parent.mkdir(parents=True, exist_ok=True)
    yaml.dump(conda_env, path)


# def write_card_and_get_type(card_path: Path, *, concept: dict, doi: str) -> Optional[str]:
#     """general version of card to be shown on bioimage.io; maybe refined after resource validation"""
#     try:
#         node = load_raw_resource_description(doi)
#
#         return node.type
#     except Exception as e:
#         warnings.warn(f"invalid resource at {doi}")
#         return None


def main(collection_folder: Path, new_resources: Path) -> int:
    updated_concepts = defaultdict(list)
    validation_cases = {"model": [], "rdf": []}
    stop = False
    soft_validation_case_limit = 230  # gh actions matrix limit: 256
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
            concept_doi = hit["conceptdoi"]
            doi = hit["doi"]  # "version" doi
            created = hit["created"]
            new_version = {"version_id": doi, "doi": doi, "created": created, "status": "pending"}

            concept_path = collection_folder / concept_doi / "concept.yaml"
            concept = write_concept(
                concept_path=concept_path,
                id_=concept_doi,
                concept_doi=concept_doi,
                version_id=doi,
                new_version=new_version,
            )
            if concept in ("blocked", "old_hit"):
                continue
            else:
                assert isinstance(concept, dict)

            rdf_urls = [file_hit["links"]["self"] for file_hit in hit["files"] if file_hit["key"] == "rdf.yaml"]
            rdf = get_rdf(rdf_urls=rdf_urls, doi=doi, concept_doi=concept_doi)

            # categorize rdf by type (to know what kind of validation to run)
            type_ = rdf.get("type")
            if type_ not in validation_cases:
                type_ = "rdf"

            if type_ == "model":
                # generate validation cases per weight format
                weight_entries = rdf.get("weights")
                if not weight_entries or not isinstance(weight_entries, dict):
                    weight_formats = [""]
                else:
                    weight_formats = list(weight_entries)

                for wf in weight_formats:
                    validation_cases[type_].append({"id": doi, "weight_format": wf})
                    write_conda_env_file(type_, rdf, wf, hit["files"], new_resources / doi / f"{wf}_env.yaml")

            else:
                validation_cases[type_].append({"id": doi})

            yaml.dump(hit, new_resources / doi / "hit.yaml")

            updated_concepts[concept_doi].append(doi)
            n_validation_cases = sum(map(len, validation_cases.values()))
            if n_validation_cases >= soft_validation_case_limit:
                warnings.warn(
                    f"Stopping after reaching soft limit {soft_validation_case_limit} with {n_validation_cases} validation cases."
                )
                stop = True
                break

        if stop:
            break

    # todo: add resources hosted on github

    for type_, cases in validation_cases.items():
        set_gh_actions_output(f"{type_}_matrix", json.dumps({"case": cases}))

    set_gh_actions_output(
        "updated_concepts_matrix",
        json.dumps(
            {"update": [{"id": k, "concept_doi": k, "new_version_ids": v} for k, v in updated_concepts.items()]}
        ),
    )
    return 0


if __name__ == "__main__":
    typer.run(main)
