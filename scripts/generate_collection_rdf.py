import json
import shutil
from datetime import datetime
from pathlib import Path
from pprint import pprint

import typer
from boltons.iterutils import remap

from bioimageio.spec.shared import yaml
from utils import iterate_known_resources

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
    "owners",
    "previous_versions",
    "rdf_source",
    "source",
    "tags",
    "type",
]


def main(
    collection: Path = Path(__file__).parent / "../collection",
    gh_pages: Path = Path(__file__).parent / "../gh-pages",
    rdf_template_path: Path = Path(__file__).parent / "../collection_rdf_template.yaml",
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

            if latest_version is None:
                latest_version = this_version
                latest_version["id"] = f"{r.resource_id}/{version_id}"  # todo: do we need to set this here?
                latest_version["previous_versions"] = []
            else:
                latest_version["previous_versions"].append(this_version)

        if latest_version is None:
            print(f"Ignoring resource {r.resource_id} without any accepted/deployed versions")
        else:
            summary = {k: latest_version[k] for k in latest_version if k in SUMMARY_FIELDS}
            if latest_version["config"]["bioimageio"].get("owners"):
                summary["owners"] = latest_version["config"]["bioimageio"]["owners"]
            rdf["collection"].append(summary)
            type_ = latest_version.get("type", "unknown")
            n_accepted[type_] = n_accepted.get(type_, 0) + 1
            n_accepted_versions[type_] = (
                n_accepted_versions.get(type_, 0) + 1 + len(latest_version["previous_versions"])
            )

    print(f"new collection rdf contains {sum(n_accepted.values())} accepted resources.")
    print("accepted resources per type:")
    pprint(n_accepted)
    print("accepted resource versions per type:")
    pprint(n_accepted_versions)

    rdf["config"] = rdf.get("config", {})
    rdf["config"]["n_resources"] = n_accepted
    rdf["config"]["n_resource_versions"] = n_accepted_versions

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
