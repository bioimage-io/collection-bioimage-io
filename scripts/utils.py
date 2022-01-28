import copy
import json
import warnings
from itertools import product
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

import requests
from ruamel.yaml import YAML

yaml = YAML(typ="safe")


def set_gh_actions_outputs(outputs: Dict[str, Union[str, Any]]):
    for name, out in outputs.items():
        set_gh_actions_output(name, out)


def set_gh_actions_output(name: str, output: Union[str, Any]):
    """set output of a github actions workflow step calling this script"""
    if isinstance(output, bool):
        output = "yes" if output else "no"

    if not isinstance(output, str):
        output = json.dumps(output)

    # escape special characters when setting github actions step output
    output = output.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::set-output name={name}::{output}")


def iterate_over_gh_matrix(matrix: Union[str, Dict[str, list]]):
    if isinstance(matrix, str):
        matrix = json.loads(matrix)

    assert isinstance(matrix, dict), matrix
    if "exclude" in matrix:
        raise NotImplementedError("matrix:exclude")

    elif "include" in matrix:
        if len(matrix) > 1:
            raise NotImplementedError("matrix:include with other keys")

        yield from matrix["include"]

    else:
        keys = list(matrix)
        for vals in product(*[matrix[k] for k in keys]):
            yield dict(zip(keys, vals))


def resolve_partners(rdf: dict) -> Tuple[List[dict], List[dict], set, set]:
    from bioimageio.spec import load_raw_resource_description
    from bioimageio.spec.collection.v0_2.raw_nodes import Collection
    from bioimageio.spec.collection.v0_2.utils import resolve_collection_entries

    current_format = "0.2.2"

    partners = []
    partner_resources = []
    updated_partners = set()
    ignored_partners = set()
    if "partners" in rdf["config"]:
        partners = copy.deepcopy(rdf["config"]["partners"])
        for idx in range(len(partners)):
            partner = partners[idx]
            try:
                partner_collection = load_raw_resource_description(partner["source"], update_to_format=current_format)
                assert isinstance(partner_collection, Collection)
            except Exception as e:
                warnings.warn(
                    f"Invalid partner source {partner['source']} (Cannot update to format {current_format}): {e}"
                )
                ignored_partners.add(f"partner[{idx}]")
                continue

            partner_id = partner.get("id") or partner_collection.id
            if not partner_id:
                warnings.warn(f"Missing partner id for partner {idx}: {partner}")
                ignored_partners.add(f"partner[{idx}]")
                continue

            if partner_collection.config:
                partners[idx].update(partner_collection.config)

            partners[idx]["id"] = partner_id

            for entry_rdf, entry_error in resolve_collection_entries(partner_collection, collection_id=partner_id):
                if entry_error:
                    warnings.warn(f"partner[{idx}] {partner_id}: {entry_error}")
                    ignored_partners.add(partner_id)
                    continue

                # Convert relative links to absolute
                if "links" in entry_rdf:
                    for idx, link in enumerate(entry_rdf["links"]):
                        if "/" not in link:
                            entry_rdf["links"][idx] = partner_id + "/" + link

                updated_partners.add(partner_id)
                partner_resources.append(
                    dict(
                        status="accepted",
                        id=entry_rdf["id"],
                        type=entry_rdf.get("type", "unknown"),
                        versions=[
                            dict(
                                name=entry_rdf.get("name", "unknown"),
                                version_id="latest",
                                version_name="latest",
                                status="accepted",
                                rdf_source=entry_rdf,
                            )
                        ],
                    )
                )

    return partners, partner_resources, updated_partners, ignored_partners


SOURCE_BASE_URL = "https://bioimage-io.github.io/collection-bioimage-io"


def get_rdf_source(collection_dir: Path, resource_id: str, version_id: str):
    updated_rdf_source = f"{SOURCE_BASE_URL}/resources/{resource_id}/{version_id}/rdf.yaml"
    try:
        rdf_source = yaml.load(requests.get(updated_rdf_source).text)
    except Exception as e:
        warnings.warn(f"failed to validate updated rdf (falling back to original rdf): {e}")

        # get original rdf source
        resource = yaml.load(collection_dir / resource_id / "resource.yaml")
        for v in resource["versions"]:
            if v["id"] == version_id:
                rdf_source = v["rdf_source"]
                break
        else:
            raise ValueError(version_id)

    return rdf_source
