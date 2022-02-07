import copy
import json
import pathlib
import warnings
from hashlib import sha256
from io import StringIO
from itertools import product
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

from marshmallow import missing
from ruamel.yaml import YAML, comments

from bare_utils import DEPLOYED_BASE_URL, get_sha256
from bioimageio.core import __version__ as bioimageio_core_version
from bioimageio.spec import (
    __version__ as bioimageio_spec_version,
    load_raw_resource_description,
    serialize_raw_resource_description_to_dict,
)
from bioimageio.spec.io_ import serialize_raw_resource_description
from bioimageio.spec.shared.utils import resolve_source


# todo: use MyYAML from bioimageio.spec. see comment below
class MyYAML(YAML):
    """add convenient improvements over YAML
    improve dump:
        - make sure to dump with utf-8 encoding. on windows encoding 'windows-1252' may otherwise be used
        - expose indentation kwargs for dump
    """

    def dump(self, data, stream=None, *, transform=None):
        if isinstance(stream, pathlib.Path):
            with stream.open("wt", encoding="utf-8") as f:
                return super().dump(data, f, transform=transform)
        else:
            return super().dump(data, stream, transform=transform)


# todo: clean up difference to bioimageio.spec.shared.yaml (diff is typ='safe'), but with 'safe' enforce_block_style does not work
yaml = MyYAML()


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


def resolve_partners(
    rdf: dict, *, current_format: str, previous_partner_hashes: Dict[str, str]
) -> Tuple[List[dict], List[dict], Dict[str, str], set]:
    from bioimageio.spec import load_raw_resource_description
    from bioimageio.spec.collection.v0_2.raw_nodes import Collection
    from bioimageio.spec.collection.v0_2.utils import resolve_collection_entries

    partners = []
    updated_partner_resources = []
    new_partner_hashes = {}
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

            partner_id: str = partner.get("id") or partner_collection.id
            if not partner_id:
                warnings.warn(f"Missing partner id for partner {idx}: {partner}")
                ignored_partners.add(f"partner[{idx}]")
                continue

            serialized_partner_collection: str = serialize_raw_resource_description(partner_collection)
            partner_hash = sha256(serialized_partner_collection.encode("utf-8")).hexdigest()
            # option to skip based on partner collection diff
            if partner_hash == previous_partner_hashes.get(partner_id):
                continue  # no change in partner collection

            new_partner_hashes[partner_id] = partner_hash
            if partner_collection.config:
                partners[idx].update(partner_collection.config)

            partners[idx]["id"] = partner_id

            for entry_idx, (entry_rdf, entry_error) in enumerate(
                resolve_collection_entries(partner_collection, collection_id=partner_id)
            ):
                if entry_error:
                    warnings.warn(f"{partner_id}[{entry_idx}]: {entry_error}")
                    continue

                # Convert relative links to absolute  # todo: move to resolve_collection_entries
                if "links" in entry_rdf:
                    for idx, link in enumerate(entry_rdf["links"]):
                        if "/" not in link:
                            entry_rdf["links"][idx] = partner_id + "/" + link

                updated_partner_resources.append(
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

    return partners, updated_partner_resources, new_partner_hashes, ignored_partners


def write_rdfs_for_resource(resource: dict, dist: Path) -> List[str]:
    """write updated version rdfs for the given resource to dist"""
    from imjoy_plugin_parser import get_plugin_as_rdf

    resource_id = resource["id"]
    updated_versions = []
    for version_info in resource["versions"]:
        if version_info["status"] == "blocked":
            continue

        # Ignore the name in the version info
        del version_info["name"]

        if isinstance(version_info["rdf_source"], dict):
            if version_info["rdf_source"].get("source", "").split("?")[0].endswith(".imjoy.html"):
                rdf_info = dict(get_plugin_as_rdf(resource["id"].split("/")[1], version_info["rdf_source"]["source"]))
            else:
                rdf_info = {}

            # Inherit the info from e.g. the collection
            rdf = version_info["rdf_source"].copy()
            rdf.update(rdf_info)
            assert missing not in rdf.values(), rdf
        elif version_info["rdf_source"].split("?")[0].endswith(".imjoy.html"):
            rdf = dict(get_plugin_as_rdf(resource["id"].split("/")[1], version_info["rdf_source"]))
            assert missing not in rdf.values(), rdf
        else:
            try:
                rdf_node = load_raw_resource_description(version_info["rdf_source"])
            except Exception as e:
                warnings.warn(f"Failed to interpret {version_info['rdf_source']} as rdf: {e}")
                try:
                    rdf = resolve_source(version_info["rdf_source"])
                    if not isinstance(rdf, dict):
                        raise TypeError(type(rdf))
                except Exception as e:
                    rdf = {
                        "invalid_original_rdf_source": version_info["rdf_source"],
                        "invalid_original_rdf_source_error": str(e),
                    }
            else:
                rdf = serialize_raw_resource_description_to_dict(rdf_node)

        if "config" not in rdf:
            rdf["config"] = {}
        if "bioimageio" not in rdf["config"]:
            rdf["config"]["bioimageio"] = {}

        # Allowing to override fields
        for k in version_info:
            # Place these fields under config.bioimageio
            if k in ["created", "doi", "status", "version_id", "version_name"]:
                rdf["config"]["bioimageio"][k] = version_info[k]
            else:
                rdf[k] = version_info[k]

        version_id = version_info["version_id"]

        if "rdf_source" in rdf and isinstance(rdf["rdf_source"], dict):
            del rdf["rdf_source"]

        if "owners" in resource:
            rdf["config"]["bioimageio"]["owners"] = resource["owners"]

        rdf["rdf_source"] = f"{DEPLOYED_BASE_URL}/rdfs/{resource_id}/{version_id}/rdf.yaml"

        updated_versions.append(version_id)
        rdf_deploy_path = dist / "rdfs" / resource_id / version_id / "rdf.yaml"
        rdf_deploy_path.parent.mkdir(parents=True, exist_ok=True)
        yaml.dump(rdf, rdf_deploy_path)
        rdf_hash = get_sha256(rdf_deploy_path)
        ts_deploy_path = rdf_deploy_path.with_name("test_summary.yaml")
        yaml.dump(
            {
                "bioimageio": dict(
                    rdf_hash=rdf_hash,
                    bioimageio_spec_version=bioimageio_spec_version,
                    bioimageio_core_version=bioimageio_core_version,
                )
            },
            ts_deploy_path,
        )

    return updated_versions


def enforce_block_style_resource(resource: dict):
    """enforce block style except for version:rdf_source, which might be an rdf dict"""
    resource = copy.deepcopy(resource)

    rdf_sources = [v.pop("rdf_source") for v in resource.get("versions", [])]
    resource = enforce_block_style(resource)
    assert len(rdf_sources) == len(resource["versions"])
    for i in range(len(rdf_sources)):
        resource["versions"][i]["rdf_source"] = rdf_sources[i]

    return resource


def enforce_block_style(data):
    """enforce block style in yaml data dump. Does not work with YAML(typ='safe')"""
    if isinstance(data, list):
        converted = comments.CommentedSeq([enforce_block_style(d) for d in data])
    elif isinstance(data, dict):
        converted = comments.CommentedMap({enforce_block_style(k): enforce_block_style(v) for k, v in data.items()})
    else:
        return data

    converted.fa.set_block_style()
    return converted
