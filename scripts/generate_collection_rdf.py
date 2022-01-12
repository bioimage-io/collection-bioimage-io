import json
from datetime import datetime
from pathlib import Path
from pprint import pprint

import requests
import typer
from boltons.iterutils import remap
from ruamel.yaml import YAML

from bioimageio.spec import load_raw_resource_description
from bioimageio.spec.io_ import serialize_raw_resource_description_to_dict
from imjoy_plugin_parser import get_plugin_as_rdf

yaml = YAML(typ="safe")

SOURCE_BASE_URL = "https://bioimage-io.github.io/collection-bioimage-io"


def main(
    collection_dir: Path = Path(__file__).parent / "../collection",
    rdf_template_path: Path = Path(__file__).parent / "../collection_rdf_template.yaml",
    dist_dir: Path = Path(__file__).parent / "../gh-pages",
):
    rdf = yaml.load(rdf_template_path)
    resources_dir = dist_dir / "resources"
    # resolve partners
    if "partners" in rdf["config"]:
        partners = rdf["config"]["partners"]
        for idx in range(len(partners)):
            partner = partners[idx]
            if partner["source"].startswith("http"):
                response = requests.get(partner["source"])
                if not response.ok:
                    raise Exception("WARNING: Failed to fetch partner config from: " + partner["source"])
                partner_info = yaml.load(response.text)
                if "config" in partner_info:
                    assert (
                        partner_info["config"]["id"] == partner["id"]
                    ), f"Partner id mismatch ({partner_info['config']['id']} != {partner['id']})"
                    partners[idx].update(partner_info["config"])
        print(f"partners updated: {len(partners)}")

    rdf["collection"] = rdf.get("collection", [])
    collection = rdf["collection"]
    assert isinstance(collection, list), type(collection)

    n_accepted = {}
    n_accepted_versions = {}
    known_resources = list(collection_dir.glob("**/resource.yaml"))
    for r_path in known_resources:
        r = yaml.load(r_path)
        if r["status"] != "accepted":
            continue
        resource_id = r["id"]
        latest_version = None
        for v in r["versions"]:
            if v["status"] != "accepted":
                continue
            if isinstance(v["source"], dict):
                this_version = v["source"]
            elif v["source"].split("?")[0].endswith(".imjoy.html"):
                this_version = dict(get_plugin_as_rdf(r["id"].split("/")[1], v["source"]))
            else:
                try:
                    rdf_node = load_raw_resource_description(v["source"])
                except Exception as e:
                    print(f"Failed to interpret {v['source']} as rdf: {e}")
                    continue
                else:
                    this_version = serialize_raw_resource_description_to_dict(rdf_node)

            this_version.update(v)
            version_sub_path = Path(resource_id) / v["version_id"]

            this_version["rdf_source"] = f"{SOURCE_BASE_URL}/resources/{resource_id}/{v['version_id']}/rdf.yaml"
            if isinstance(this_version["source"], dict):
                this_version["source"] = this_version["rdf_source"]

            v_path = resources_dir / version_sub_path / "rdf.yaml"
            v_path.parent.mkdir(parents=True, exist_ok=True)
            yaml.dump(this_version, v_path)

            # add validation summaries
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
            print(f"Ignoring resource at {r_path} without any accepted versions")
        else:
            collection.append(latest_version)
            type_ = latest_version.get("type", "unknown")
            n_accepted[type_] = n_accepted.get(type_, 0) + 1
            n_accepted_versions[type_] = (
                n_accepted_versions.get(type_, 0) + 1 + len(latest_version["previous_versions"])
            )

    print(f"new collection rdf contains {sum(n_accepted.values())} accepted of {len(known_resources)} known resources.")
    print("accepted resources per type:")
    pprint(n_accepted)
    print("accepted resource versions per type:")
    pprint(n_accepted_versions)

    rdf["config"] = rdf.get("config", {})
    rdf["config"]["n_resources"] = n_accepted
    rdf["config"]["n_resource_versions"] = n_accepted_versions
    rdf_path = dist_dir / "rdf.yaml"
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
