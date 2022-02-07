import json
import warnings
from datetime import datetime
from pathlib import Path
from pprint import pprint

import typer
from boltons.iterutils import remap

from bioimageio.spec.shared import yaml

SUMMARY_FIELDS = [
    "id",
    "icon",
    "owners",
    "authors",
    "covers",
    "description",
    "license",
    "links",
    "name",
    "rdf_source",
    "source",
    "tags",
    "type",
    "download_url",
    "badges",
    "github_repo",
]


def main(
    collection: Path = Path(__file__).parent / "../collection",
    gh_pages_dir: Path = Path(__file__).parent / "../gh-pages",
    rdf_template_path: Path = Path(__file__).parent / "../collection_rdf_template.yaml",
    dist: Path = Path(__file__).parent / "../dist",
):
    rdf = yaml.load(rdf_template_path)
    rdf["collection"] = rdf.get("collection", [])
    rdf_collection = rdf["collection"]
    assert isinstance(rdf_collection, list), type(rdf_collection)

    if "partners" in rdf["config"]:
        # load resolved partner details
        partner_details_path = gh_pages_dir / "partner_details.yaml"
        if partner_details_path.exists():
            rdf["config"]["partners"] = yaml.load(partner_details_path)
        else:
            warnings.warn(f"Missing evaluated partner details at {partner_details_path}")

    n_accepted = {}
    n_accepted_versions = {}
    collection_resources = [yaml.load(r_path) for r_path in collection.glob("**/resource.yaml")]
    partner_resources = [yaml.load(r_path) for r_path in (gh_pages_dir / "partner_collection").glob("**/resource.yaml")]
    known_resources = [r for r in partner_resources + collection_resources if r["status"] == "accepted"]
    for r in known_resources:
        resource_id = r["id"]
        latest_version = None
        for version_info in r["versions"]:
            if version_info["status"] != "accepted":
                continue

            updated_rdf_source = gh_pages_dir / "rdfs" / resource_id / version_info["version_id"] / "rdf.yaml"
            if not updated_rdf_source.exists():
                warnings.warn(f"skipping undeployed rdf {updated_rdf_source}")
                continue

            this_version = yaml.load(updated_rdf_source)

            if latest_version is None:
                latest_version = this_version
                latest_version["id"] = r["id"]
                latest_version["previous_versions"] = []
            else:
                latest_version["previous_versions"].append(this_version)

        if latest_version is None:
            print(f"Ignoring resource {resource_id} without any accepted versions")
        else:
            summary = {k: latest_version[k] for k in latest_version if k in SUMMARY_FIELDS}
            if latest_version["config"]["bioimageio"].get("owners"):
                summary["owners"] = latest_version["config"]["bioimageio"]["owners"]
            rdf_collection.append(summary)
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
    rdf_path = dist / "rdf.yaml"
    rdf_path.parent.mkdir(exist_ok=True)
    yaml.dump(rdf, rdf_path)

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

    rdf = remap(rdf, convert_for_json)
    with open(rdf_path.with_suffix(".json"), "w") as f:
        json.dump(rdf, f, allow_nan=False, indent=2)


if __name__ == "__main__":
    typer.run(main)
