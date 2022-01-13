import json
from datetime import datetime
from pathlib import Path
from pprint import pprint

import typer
from boltons.iterutils import remap
from marshmallow import missing
from ruamel.yaml import YAML

from bioimageio.spec import load_raw_resource_description
from bioimageio.spec.io_ import serialize_raw_resource_description_to_dict
from imjoy_plugin_parser import get_plugin_as_rdf
from utils import resolve_partners

yaml = YAML(typ="safe")

SOURCE_BASE_URL = "https://bioimage-io.github.io/collection-bioimage-io"


def main(
    collection_dir: Path = Path(__file__).parent / "../collection",
    rdf_template_path: Path = Path(__file__).parent / "../collection_rdf_template.yaml",
    gh_pages_dir: Path = Path(__file__).parent / "../gh-pages",
    dist: Path = Path(__file__).parent / "../gh-pages",
):
    rdf = yaml.load(rdf_template_path)
    resources_dir = gh_pages_dir / "resources"

    partners, partner_resources, updated_partners, ignored_partners = resolve_partners(rdf)
    if "partners" in rdf["config"]:
        rdf["config"]["partners"] = partners
        print(f"{len(updated_partners)}/{len(updated_partners | ignored_partners)} partners updated")

    rdf["collection"] = rdf.get("collection", [])
    collection = rdf["collection"]
    assert isinstance(collection, list), type(collection)

    n_accepted = {}
    n_accepted_versions = {}
    collection_resources = [yaml.load(r_path) for r_path in collection_dir.glob("**/resource.yaml")]
    collection_resources = [r for r in collection_resources if r["status"] == "accepted"]
    known_resources = partner_resources + collection_resources
    for r in known_resources:
        resource_id = r["id"]
        latest_version = None
        for v in r["versions"]:
            if v["status"] != "accepted":
                continue
            if isinstance(v["source"], dict):
                if v["source"].get("source", "").split("?")[0].endswith(".imjoy.html"):
                    this_version = dict(get_plugin_as_rdf(r["id"].split("/")[1], v["source"]["source"]))
                else:
                    this_version = {}

                this_version.update(v["source"])
                assert missing not in this_version.values(), this_version
            elif v["source"].split("?")[0].endswith(".imjoy.html"):
                this_version = dict(get_plugin_as_rdf(r["id"].split("/")[1], v["source"]))
                assert missing not in this_version.values(), this_version
            else:
                try:
                    rdf_node = load_raw_resource_description(v["source"])
                except Exception as e:
                    print(f"Failed to interpret {v['source']} as rdf: {e}")
                    continue
                else:
                    this_version = serialize_raw_resource_description_to_dict(rdf_node)

            this_version.update(v)
            this_version["rdf_source"] = f"{SOURCE_BASE_URL}/resources/{resource_id}/{v['version_id']}/rdf.yaml"
            if isinstance(this_version["source"], dict):
                this_version["source"] = this_version["rdf_source"]

            v_path = resources_dir / resource_id / v["version_id"] / "rdf.yaml"
            v_path.parent.mkdir(parents=True, exist_ok=True)
            with v_path.open("wt", encoding="utf-8") as f:
                yaml.dump(this_version, f)

            # add validation summaries to this version in the collection
            val_summaries = {}
            for val_path in v_path.parent.glob("validation_summary_*.yaml"):
                name = val_path.stem.replace("validation_summary_", "")
                val_sum = yaml.load(val_path)
                if not isinstance(val_sum, dict):
                    val_sum = {"output": val_sum}

                val_summaries[name] = {k: v for k, v in val_sum.items() if k != "source_name"}

            this_version["validation_summaries"] = val_summaries

            if latest_version is None:
                latest_version = this_version
                latest_version["id"] = r["id"]
                latest_version["previous_versions"] = []
            else:
                latest_version["previous_versions"].append(this_version)

        if latest_version is None:
            print(f"Ignoring resource {resource_id} without any accepted versions")
        else:
            collection.append(latest_version)
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
        json.dump(rdf, f, allow_nan=False)


if __name__ == "__main__":
    typer.run(main)
