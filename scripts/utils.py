import copy
import dataclasses
import json
import pathlib
import shutil
import warnings
from hashlib import sha256
from itertools import product
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Generator, List, Optional, Sequence, Tuple, Union
from urllib.parse import urlsplit

import numpy
import requests
from bare_utils import DEPLOYED_BASE_URL, GH_API_URL
from bioimageio.spec import (
    load_raw_resource_description,
    serialize_raw_resource_description_to_dict,
)
from bioimageio.spec.collection.v0_2.raw_nodes import Collection
from bioimageio.spec.collection.v0_2.utils import resolve_collection_entries
from bioimageio.spec.partner.utils import enrich_partial_rdf_with_imjoy_plugin
from ruamel.yaml import YAML, comments


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
    partners = []
    updated_partner_resources = []
    new_partner_hashes = {}
    ignored_partners = set()
    if "partners" in rdf["config"]:
        partners = copy.deepcopy(rdf["config"]["partners"])
        for idx in range(len(partners)):
            partner = partners[idx]
            try:
                partner_collection = load_raw_resource_description(
                    f"https://raw.githubusercontent.com/{partner['repository']}/{partner['branch']}/{partner['collection_file_name']}",
                    update_to_format=current_format,
                )
                assert isinstance(partner_collection, Collection)
            except Exception as e:
                warnings.warn(
                    f"Invalid partner source {partner.get('source')} (Cannot update to format {current_format}): {e}"
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

            r = requests.get(
                f"{ GH_API_URL }/repos/{ partner['repository'] }/commits/{ partner['branch'] }",
                headers=dict(Accept="application/vnd.github.v3+json"),
            )
            try:
                r.raise_for_status()
            except requests.HTTPError as e:
                print(e)
                continue

            if partner_collection.config:
                partners[idx].update(partner_collection.config)

            partners[idx]["id"] = partner_id
            partner_hash = r.json()["sha"]
            # option to skip based on partner collection diff
            if partner_hash == previous_partner_hashes.get(partner_id):
                continue  # no change in partner collection

            new_partner_hashes[partner_id] = partner_hash
            for entry_idx, (entry_rdf, entry_error) in enumerate(
                resolve_collection_entries(
                    partner_collection,
                    collection_id=partner_id,
                    enrich_partial_rdf=enrich_partial_rdf_with_imjoy_plugin,
                )
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
    resource_id = resource["id"]
    updated_versions = []
    resource_info = enrich_partial_rdf_with_imjoy_plugin(resource, pathlib.Path())
    for version_info in resource.get("versions", []):
        version_id = version_info["version_id"]
        if (
            resource["status"] == "blocked"
            or version_info["status"] == "blocked"
            or only_for_version_id is not None
            and only_for_version_id != version_id
        ):
            continue

        version_info = enrich_partial_rdf_with_imjoy_plugin(version_info, pathlib.Path())

        rdf = dict(resource_info)  # rdf is based on resource info
        rdf.update(version_info)  # version specific info overwrites resource info

        rdf.pop("versions", None)

        # ensure config:bioimageio exists
        if "config" not in rdf:
            rdf["config"] = {}
        if "bioimageio" not in rdf["config"]:
            rdf["config"]["bioimageio"] = {}

        # Move bioimageio specific fields to config.bioimageio
        for k in ["created", "doi", "status", "version_id", "version_name", "owners", "nickname", "nickname_icon"]:
            if k in rdf:
                rdf["config"]["bioimageio"][k] = rdf.pop(k)

        # remove rdf source as it has been processed and might block loading if it is invalid on its own
        rdf.pop("rdf_source", None)

        try:
            # resolve relative paths of remote rdf_source
            orig_rdf = rdf
            rdf_node = load_raw_resource_description(rdf)
            rdf = serialize_raw_resource_description_to_dict(
                rdf_node,
                convert_absolute_paths=False,  # todo: we should not have any abs paths, but just in case we should convert them.. this needs a spec update though (underway)
            )
        except Exception as e:
            warnings.warn(f"remote files could not be resolved for invalid RDF; error: {e}")
        else:
            # round-trip removes unknown fields for some RDF types, but we want to keep them
            for k, v in orig_rdf.items():
                if k not in rdf:
                    rdf[k] = v

        # overwrite id and rdf_source
        rdf["id"] = f"{resource_id}/{version_id}"
        rdf["rdf_source"] = f"{DEPLOYED_BASE_URL}/rdfs/{resource_id}/{version_id}/rdf.yaml"

        rdf.pop("root_path", None)

        # sort rdf to avoid random diffs
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
    assert len(rdf_sources) == len(resource.get("versions", []))
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
    rdf: Dict[str, Any]
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
        for v_info in known_r.info.get("versions", []):
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


def load_yaml_dict(path: Path, raise_missing_keys: Sequence[str]) -> Optional[Dict]:
    if not path.exists():
        return None

    data = yaml.load(path)
    if not isinstance(data, dict):
        raise TypeError(f"Expected {path} to hold a dictionary, but got {type(data)}")

    missing = [k for k in raise_missing_keys if k not in data]
    if missing:
        raise KeyError(f"Expected missing keys {missing} in {path}")

    return data


def downsize_image(image_path: Path, output_path: Path, size: Tuple[int, int]):
    """downsize or copy an image"""
    from PIL import Image

    try:
        with Image.open(image_path) as img:
            img.thumbnail(size)
            img.save(output_path, "PNG")
    except Exception as e:
        warnings.warn(str(e))
        shutil.copy(image_path, output_path)


def deploy_thumbnails(rdf_like: Dict[str, Any], dist: Path, gh_pages: Path, resource_id: str, version_id: str) -> None:
    import pooch

    dist /= f"rdfs/{resource_id}/{version_id}"
    gh_pages /= f"rdfs/{resource_id}/{version_id}"
    dist.mkdir(exist_ok=True, parents=True)
    covers: Union[Any, List[Any]] = rdf_like.get("covers")
    if isinstance(covers, list):
        for i, cover_url in enumerate(covers):
            if not isinstance(cover_url, str) or cover_url.startswith(DEPLOYED_BASE_URL):
                continue  # invalid or already cached

            cover_file_name = PurePosixPath(urlsplit(cover_url.strip("/content")).path).name
            if not (gh_pages / cover_file_name).exists():
                try:
                    downloaded_cover = Path(pooch.retrieve(cover_url, None))  # type: ignore
                except Exception as e:
                    warnings.warn(str(e))
                    continue

                downsize_image(downloaded_cover, dist / cover_file_name, size=(600, 340))

            rdf_like["covers"][i] = f"{DEPLOYED_BASE_URL}/rdfs/{resource_id}/{version_id}/{cover_file_name}"

    badges: Union[Any, List[Union[Any, Dict[Any, Any]]]] = rdf_like.get("badges")
    if isinstance(badges, list):
        for i, badge in enumerate(badges):
            if not isinstance(badge, dict):
                continue

            icon = badge.get("icon")
            if not isinstance(icon, str) or not icon.startswith("https://zenodo.org/api"):
                # only cache badges stored on zenodo
                continue

            try:
                downloaded_icon = Path(pooch.retrieve(icon, None, path=dist))  # type: ignore
            except Exception as e:
                warnings.warn(str(e))
                continue

            icon_file_name = PurePosixPath(urlsplit(icon.strip("/content")).path).name
            downsize_image(downloaded_icon, dist / icon_file_name, size=(320, 320))

            rdf_like["badges"][i]["icon"] = f"{DEPLOYED_BASE_URL}/rdfs/{resource_id}/{version_id}/{icon_file_name}"
