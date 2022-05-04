import copy
import dataclasses
import json
import pathlib
import warnings
from hashlib import sha256
from itertools import product
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple, Union

import numpy
from marshmallow import missing
from ruamel.yaml import YAML, comments

from bare_utils import DEPLOYED_BASE_URL
from bioimageio.spec import load_raw_resource_description, serialize_raw_resource_description_to_dict
from bioimageio.spec.io_ import serialize_raw_resource_description
from bioimageio.spec.shared import BIOIMAGEIO_COLLECTION, resolve_rdf_source, resolve_source


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


with (Path(__file__).parent / "../animals.yaml").open(encoding="utf-8") as f:
    ANIMALS: Dict[str, str] = yaml.load(f)


ADJECTIVES: Tuple[str] = tuple((Path(__file__).parent / "../adjectives.txt").read_text().split())

# collect known nicknames independent of resource status (to avoid nickname conflicts if resources are unblocked)
KNOWN_NICKNAMES = [
    yaml.load(p).get("nickname") for p in (Path(__file__).parent / "../collection").glob("**/resource.yaml")
]
# note: may be appended to by 'get_animal_nickname'


def get_animal_nickname() -> Tuple[str, str]:
    """get animal nickname and associated icon"""
    for _ in range(100000):
        animal_adjective = numpy.random.choice(ADJECTIVES)
        animal_name = numpy.random.choice(list(ANIMALS.keys()))
        nickname = f"{animal_adjective}-{animal_name}"
        if nickname not in KNOWN_NICKNAMES:
            break
    else:
        raise RuntimeError("Could not find free nickname")

    KNOWN_NICKNAMES.append(nickname)
    return nickname, ANIMALS[animal_name]


_NICKNAME_DASHES = tuple(["-" + a for a in ANIMALS if "-" in a] + ["-"])


def split_animal_nickname(nickname: str) -> Tuple[str, str]:
    """split an animal nickname into adjective and animal name"""
    for d in _NICKNAME_DASHES:
        idx = nickname.rfind(d)
        if idx != -1:
            break
    else:
        raise ValueError(f"Missing dash in nickname {nickname}")

    return nickname[:idx], nickname[idx + 1 :]


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

            partner_id: str = partner.get("id")
            if partner_id is None:
                partner_id = partner_collection.id
            else:
                partner_collection.id = partner_id  # overwrite partner collection id

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

                assert hasattr(entry_rdf, "id")
                updated_partner_resources.append(
                    dict(
                        status="accepted",
                        id=entry_rdf.id,  # type: ignore
                        type=entry_rdf.type,
                        versions=[
                            dict(
                                name=entry_rdf.name,
                                version_id="latest",
                                version_name="latest",
                                status="accepted",
                                rdf_source=serialize_raw_resource_description_to_dict(entry_rdf),
                            )
                        ],
                    )
                )

    return partners, updated_partner_resources, new_partner_hashes, ignored_partners


def rec_sort(obj):
    if isinstance(obj, dict):
        return {k: rec_sort(obj[k]) for k in sorted(obj)}
    elif isinstance(obj, (list, tuple)):
        return type(obj)([rec_sort(v) for v in obj])
    else:
        return obj


def write_rdfs_for_resource(resource: dict, dist: Path, only_for_version_id: Optional[str] = None) -> List[str]:
    """write updated version rdfs for the given resource to dist

    Args:
        resource: resource info
        dist: output path
        only_for_version_id: (if not None) only write rdf for specific version

    Returns: list of updated version_ids

    """
    from imjoy_plugin_parser import get_plugin_as_rdf

    resource_id = resource["id"]
    updated_versions = []
    for resource_version in resource["versions"]:
        version_info = {k: v for k, v in resource.items() if k != "versions"}
        version_info.update(resource_version)
        version_id = version_info["version_id"]
        if version_info["status"] == "blocked" or only_for_version_id is not None and only_for_version_id != version_id:
            continue

        if isinstance(version_info["rdf_source"], dict):
            if version_info["rdf_source"].get("source", "").split("?")[0].endswith(".imjoy.html"):
                enriched_version_info = dict(
                    get_plugin_as_rdf(resource["id"], version_info["rdf_source"]["source"])
                )
                if resource["id"].startswith('imjoy'):
                    print(enriched_version_info)
                version_info.update(enriched_version_info)

            # Inherit the info from the collection
            rdf = version_info["rdf_source"].copy()
        elif version_info["rdf_source"].split("?")[0].endswith(".imjoy.html"):
            enriched_version_info = dict(get_plugin_as_rdf(resource["id"], version_info["rdf_source"]))
            version_info.update(enriched_version_info)
            rdf = {}
        else:
            try:
                rdf, rdf_name, rdf_root = resolve_rdf_source(version_info["rdf_source"])
                if not isinstance(rdf, dict):
                    raise TypeError(type(rdf))
                rdf["root_path"] = rdf_root  # we use this after updating the rdf to resolve remote sources
            except Exception as e:
                warnings.warn(f"Failed to load {version_info['rdf_source']}: {e}")
                rdf = {
                    "invalid_original_rdf_source": version_info["rdf_source"],
                    "invalid_original_rdf_source_error": str(e),
                }

        if "config" not in rdf:
            rdf["config"] = {}
        if "bioimageio" not in rdf["config"]:
            rdf["config"]["bioimageio"] = {}

        # Allowing to override fields
        for k in version_info:
            # Place these fields under config.bioimageio
            if k in ["created", "doi", "status", "version_id", "version_name", "owners", "nickname", "nickname_icon"]:
                rdf["config"]["bioimageio"][k] = version_info[k]
            else:
                rdf[k] = version_info[k]

        if "rdf_source" in rdf and isinstance(rdf["rdf_source"], dict):
            del rdf["rdf_source"]

        if "owners" in resource:
            rdf["config"]["bioimageio"]["owners"] = resource["owners"]

        rdf["id"] = f"{resource_id}/{version_id}"
        rdf["rdf_source"] = f"{DEPLOYED_BASE_URL}/rdfs/{resource_id}/{version_id}/rdf.yaml"

        # resolve file paths relative to remote resource location
        if "root_path" in rdf:
            try:
                # a round-trip will resolve all local paths to urls if 'root_path' is a url
                rdf_node = load_raw_resource_description(rdf)
                rdf = serialize_raw_resource_description_to_dict(rdf_node)
            except Exception as e:
                warnings.warn(f"Failed round-trip to resolve any remote sources: {e}")

        assert missing not in rdf.values(), rdf

        # sort rdf
        rdf = rec_sort(rdf)

        updated_versions.append(version_id)
        rdf_deploy_path = dist / "rdfs" / resource_id / version_id / "rdf.yaml"
        rdf_deploy_path.parent.mkdir(parents=True, exist_ok=True)
        yaml.dump(rdf, rdf_deploy_path)

    return updated_versions


def enforce_block_style_resource(resource: dict):
    """enforce block style except for version:rdf_source, which might be an rdf dict"""
    resource = rec_sort(copy.deepcopy(resource))

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


@dataclasses.dataclass
class KnownResource:
    resource_id: str
    path: Path
    info: Dict[str, Any]
    info_sha256: Optional[str]  # None if from partner
    partner_resource: bool


@dataclasses.dataclass
class KnownResourceVersion:
    resource: KnownResource
    resource_id: str
    version_id: str
    info: Dict[str, Any]
    rdf: dict
    rdf_sha256: Optional[str]
    rdf_path: Path


def get_sha256_and_yaml(p: Path):
    rb = p.open("rb").read()
    return sha256(rb).hexdigest(), yaml.load(rb.decode("utf-8"))


def iterate_known_resources(
    collection: Path, gh_pages: Path, resource_id: str = "**", status: Optional[str] = None
) -> Generator[KnownResource, None, None]:
    for p in sorted((gh_pages / "partner_collection").glob(f"{resource_id}/resource.yaml")):
        info = yaml.load(p)
        yield KnownResource(resource_id=info["id"], path=p, info=info, info_sha256=None, partner_resource=True)

    for p in sorted(collection.glob(f"{resource_id}/resource.yaml")):
        info_sha256, info = get_sha256_and_yaml(p)
        if status is None or info["status"] == status:
            yield KnownResource(
                resource_id=info["id"], path=p, info=info, info_sha256=info_sha256, partner_resource=False
            )


def iterate_known_resource_versions(
    collection: Path, gh_pages: Path, resource_id: str = "**", status: Optional[str] = None
) -> Generator[KnownResourceVersion, None, None]:
    for known_r in iterate_known_resources(
        collection=collection, gh_pages=gh_pages, resource_id=resource_id, status=status
    ):
        for v_info in known_r.info["versions"]:
            if status is None or v_info["status"] == status:
                v_id = v_info["version_id"]
                rdf_path = gh_pages / "rdfs" / known_r.resource_id / v_id / "rdf.yaml"
                if rdf_path.exists():
                    rdf_sha256, rdf = get_sha256_and_yaml(rdf_path)  # todo: do we really need to load rdf?
                    yield KnownResourceVersion(
                        resource=known_r,
                        resource_id=known_r.resource_id,
                        version_id=v_id,
                        info=v_info,
                        rdf=rdf,
                        rdf_sha256=rdf_sha256,
                        rdf_path=rdf_path,
                    )
                else:
                    warnings.warn(f"skipping undeployed r: {known_r.resource_id} v: {v_id}")
