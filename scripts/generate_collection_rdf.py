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
SUMMARY_FIELDS = ["id", "icon", "owners", "authors", "covers", "description", "license", "links", "name", "rdf_source", "source", "tags", "type", "download_url", "badges", "github_repo"]

def main(
    collection_dir: Path = Path(__file__).parent / "../collection",
    rdf_template_path: Path = Path(__file__).parent / "../collection_rdf_template.yaml",
    gh_pages_dir: Path = Path(__file__).parent / "../gh-pages",
    dist: Path = Path(__file__).parent / "../dist",
):
    rdf = yaml.load(rdf_template_path)

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
        for version_info in r["versions"]:
            if version_info["status"] != "accepted":
                continue

            # Ignore the name in the version info
            del version_info["name"]

            if isinstance(version_info["rdf_source"], dict):
                if version_info["rdf_source"].get("source", "").split("?")[0].endswith(".imjoy.html"):
                    rdf_info = dict(get_plugin_as_rdf(r["id"].split("/")[1], version_info["rdf_source"]["source"]))
                else:
                    rdf_info = {}

                # Inherit the info from e.g. the collection
                this_version = version_info["rdf_source"].copy()
                this_version.update(rdf_info)
                assert missing not in this_version.values(), this_version
            elif version_info["rdf_source"].split("?")[0].endswith(".imjoy.html"):
                this_version = dict(get_plugin_as_rdf(r["id"].split("/")[1], version_info["rdf_source"]))
                assert missing not in this_version.values(), this_version
            else:
                try:
                    rdf_node = load_raw_resource_description(version_info["rdf_source"])
                except Exception as e:
                    print(f"Failed to interpret {version_info['rdf_source']} as rdf: {e}")
                    continue
                else:
                    this_version = serialize_raw_resource_description_to_dict(rdf_node)

            if "config" not in this_version:
                this_version["config"] = {}
            if "bioimageio" not in this_version["config"]:
                this_version["config"]["bioimageio"] = {}

            # Allowing to override fields
            for k in version_info:
                # Place these fields under config.bioimageio
                if k in ["created", "doi", "status", "version_id", "version_name"]:
                    this_version["config"]["bioimageio"][k] = version_info[k]
                else:
                    this_version[k] = version_info[k]

            if "rdf_source" in this_version and isinstance(this_version["rdf_source"], dict):
                del this_version["rdf_source"]
            
            if "rdf_source" not in this_version:
                this_version["rdf_source"] = f"{SOURCE_BASE_URL}/resources/{resource_id}/{version_info['version_id']}/rdf.yaml"

            if "owners" in r:
                this_version["config"]["bioimageio"]["owners"] = r["owners"]

            v_deploy_path = dist / "resources" / resource_id / version_info["version_id"] / "rdf.yaml"
            v_deploy_path.parent.mkdir(parents=True, exist_ok=True)
            with v_deploy_path.open("wt", encoding="utf-8") as f:
                yaml.dump(this_version, f)
            
            this_version["rdf_source"] = f"{SOURCE_BASE_URL}/resources/{resource_id}/{version_info['version_id']}/rdf.yaml"

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
            collection.append(summary)
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
