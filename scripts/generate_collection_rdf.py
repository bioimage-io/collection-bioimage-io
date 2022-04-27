import json
import shutil
from datetime import datetime
from pathlib import Path
from pprint import pprint

import typer
from boltons.iterutils import remap

from bioimageio.spec.shared import yaml
from utils import iterate_known_resources, rec_sort

SUMMARY_FIELDS = [
    "authors",
    "badges",
    "covers",
    "description",
    "download_url",
    "github_repo",
    "icon",
    "id",
    "license",
    "links",
    "name",
    "rdf_source",
    "source",
    "tags",
    "type",
    "versions",
]

SUMMARY_FIELDS_FROM_CONFIG_BIOIMAGEIO = [
    "nickname",
    "nickname_icon",
    "owners",
]


def main(
    collection: Path = Path(__file__).parent / "../collection",
    gh_pages: Path = Path(__file__).parent / "../gh-pages",
    rdf_template_path: Path = Path(__file__).parent / "../collection_rdf_template.yaml",  # todo: rename (not a valid rdf)
    dist: Path = Path(__file__).parent / "../dist",
):
    rdf = yaml.load(rdf_template_path)
    rdf["collection"] = rdf.get("collection", [])
    assert isinstance(rdf["collection"], list), type(rdf["collection"])

    if "partners" in rdf["config"]:
        # load resolved partner details
        partner_details_path = gh_pages / "partner_details.json"
        if partner_details_path.exists():
            with partner_details_path.open() as f:
                rdf["config"]["partners"] = json.load(f)
        else:
            print(f"Missing evaluated partner details at {partner_details_path}")

    n_accepted = {}
    n_accepted_versions = {}
    for r in iterate_known_resources(collection=collection, gh_pages=gh_pages):
        latest_version = None
        for version_info in r.info["versions"]:
            if version_info["status"] != "accepted":
                continue

            version_id = version_info["version_id"]
            updated_rdf_source = gh_pages / "rdfs" / r.resource_id / version_id / "rdf.yaml"
            if not updated_rdf_source.exists():
                print(f"skipping undeployed rdf: {r.resource_id}/{version_id}")
                continue

            this_version = yaml.load(updated_rdf_source)
            if this_version is None:
                print(f"skipping empty rdf: {r.resource_id}/{version_id}")
                continue

            assert version_id == this_version["id"].split("/")[-1]
            assert r.resource_id == this_version["id"][: -(len(version_id) + 1)]

            if latest_version is None:
                latest_version = this_version
                latest_version["id"] = r.resource_id
                latest_version["versions"] = [version_id]
            else:
                latest_version["versions"].append(version_id)

        if latest_version is None:
            print(f"Ignoring resource {r.resource_id} without any accepted/deployed versions")
        else:
            summary = {k: latest_version[k] for k in latest_version if k in SUMMARY_FIELDS}
            for k in latest_version["config"]["bioimageio"]:
                if k in SUMMARY_FIELDS_FROM_CONFIG_BIOIMAGEIO:
                    summary[k] = latest_version["config"]["bioimageio"][k]

            rdf["collection"].append(summary)
            type_ = latest_version.get("type", "unknown")
            n_accepted[type_] = n_accepted.get(type_, 0) + 1
            n_accepted_versions[type_] = n_accepted_versions.get(type_, 0) + 1 + len(latest_version["versions"])

    print(f"new collection rdf contains {sum(n_accepted.values())} accepted resources.")
    print("accepted resources per type:")
    pprint(n_accepted)
    print("accepted resource versions per type:")
    pprint(n_accepted_versions)

    rdf["config"] = rdf.get("config", {})
    rdf["config"]["n_resources"] = n_accepted
    rdf["config"]["n_resource_versions"] = n_accepted_versions

    # check for unique nicknames
    nicknames = [e["nickname"] for e in rdf["collection"] if "nickname" in e]
    duplicate_nicknames = [nick for i, nick in enumerate(nicknames) if nick in nicknames[:i]]
    if duplicate_nicknames:
        raise ValueError(f"Duplicate nicknames: {duplicate_nicknames}")

    rdf_path = dist / "rdf.yaml"
    rdf_path.parent.mkdir(exist_ok=True)
    yaml.dump(rec_sort(rdf), rdf_path)

    def convert_for_json(p, k, v):
        """convert anything not json compatible"""
        # replace nans
        number_strings = ["-inf", "inf", "nan"]
        for n in number_strings:
            if v == float(n):
                return k, n

        if isinstance(v, datetime):
            return k, v.isoformat()

        return True

    rdf_path = dist / "collection.json"
    rdf = remap(rdf, convert_for_json)
    rdf_path.parent.mkdir(exist_ok=True)
    with open(rdf_path, "w") as f:
        json.dump(rdf, f, allow_nan=False, indent=2, sort_keys=True)

    shutil.copy(str(rdf_path), str(rdf_path.with_name("rdf.json")))  # deprecated; todo: remove


if __name__ == "__main__":
    typer.run(main)
