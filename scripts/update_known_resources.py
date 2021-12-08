import json
import sys
import warnings
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Literal, Union

import requests
from ruamel.yaml import YAML

from dataclass_argparse import TypedNamespace

yaml = YAML(typ="safe")


@dataclass
class Args(TypedNamespace):
    collection: Path = field(default=Path("collection"), metadata=dict(help="path to collection folder"))
    # new_resources: Path = field(default=Path("new_resources"), metadata=dict(help="folder to save new resources to"))


parser = Args.get_parser("Fetch new bioimage.io resources.", add_help=True)


def set_gh_actions_output(name: str, output: str):
    """set output of a github actions workflow step calling this script"""
    # escape special characters when setting github actions step output
    output = output.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::set-output name={name}::{output}")


def write_concept(
    *, concept_path: Path, concept_doi: str, doi: str, new_version: dict
) -> Union[dict, Literal["old_hit", "blocked"]]:
    if concept_path.exists():
        concept = yaml.load(concept_path)
        assert isinstance(concept, dict)
        if concept["status"] == "blocked":
            return "blocked"
        elif concept["status"] in ("accepted", "pending"):
            assert concept[
                "versions"
            ], f"expected at least one existing version for {concept['status']} concept {concept_doi}"
        else:
            raise ValueError(concept["status"])

        for known_version in concept["versions"]:
            if known_version["doi"] == doi:
                # fetched resource is known; assume all following older resources have been processed earlier
                return "old_hit"

        # extend concept by new version
        concept["pending_versions"].append(new_version)
    else:  # create new concept
        concept = {"status": "pending", "versions": [new_version]}

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
        rdf = yaml.load(r.text)
        if not isinstance(rdf, dict):
            warnings.warn(
                f"Found invalid rdf.yaml (not a dict) for new version {doi} of {concept_doi}; " "writing empty rdf.yaml"
            )
            rdf = {}
    else:
        warnings.warn(
            f"Found {len(rdf_urls)} rdf.yaml files for new version {doi} of {concept_doi}; " "writing empty rdf.yaml"
        )
        rdf = {}

    return rdf


# def write_card_and_get_type(card_path: Path, *, concept: dict, doi: str) -> Optional[str]:
#     """general version of card to be shown on bioimage.io; maybe refined after resource validation"""
#     try:
#         node = load_raw_resource_description(doi)
#
#         return node.type
#     except Exception as e:
#         warnings.warn(f"invalid resource at {doi}")
#         return None

def main(args: Args):
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
            new_version = {"doi": doi, "created": created, "status": "pending"}

            concept_path = args.collection / concept_doi / "concept.yaml"
            concept = write_concept(
                concept_path=concept_path, concept_doi=concept_doi, doi=doi, new_version=new_version
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
                    validation_cases[type_].append({"doi": doi, "weight_format": wf})

            else:
                validation_cases[type_].append({"doi": doi})

            updated_concepts[concept_doi].append(doi)
            if n_validation_cases := sum(map(len, validation_cases.values())) >= soft_validation_case_limit:
                warnings.warn(f"Stopping after reaching soft limit {soft_validation_case_limit} with {n_validation_cases} validation cases.")
                stop = True
                break

        if stop:
            break

    for type_, cases in validation_cases.items():
        set_gh_actions_output(f"{type_}_matrix", json.dumps({"validation_case": cases}))

    set_gh_actions_output(
        "updated_concepts_matrix",
        json.dumps({"update": [{"concept_doi": k, "new_dois": v} for k, v in updated_concepts.items()]}),
    )


if __name__ == "__main__":
    args = parser.parse_args()
    sys.exit(main(args))
