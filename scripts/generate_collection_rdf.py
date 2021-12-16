import json
import warnings
from pathlib import Path

import typer
from ruamel.yaml import YAML

yaml = YAML(typ="safe")


def main() -> int:
    collection_path = Path("main/collection")
    resource_path = Path("gh-pages/resources")
    rdf = yaml.load(Path("main/collection_rdf_template.yaml"))

    for r_path in collection_path.glob("**/resource.yaml"):
        r = yaml.load(r_path)
        if r["status"] != "accepted":
            continue

        latest_version = None
        for v in r["versions"]:
            if v["status"] != "accepted":
                continue

            v_path = resource_path / v["version_id"] / "rdf.yaml"
            if latest_version is None:
                latest_version = yaml.load(v_path)
                if isinstance(latest_version, dict):
                    latest_version["previous_versions"] = []
                else:
                    latest_version = None
                    warnings.warn(f"ignoring non-dict {v_path}")
            else:
                latest_version["previous_versions"].append(yaml.load(v_path))

        if latest_version is None:
            warnings.warn(f"Ignoring resource at {r_path} without any accepted versions")
        else:
            type_ = latest_version.get("type", "unknown")
            type_list = rdf.get(type_)
            if isinstance(type_list, list):
                type_list.append(latest_version)
            else:
                warnings.warn(f"ignoring resource {r_path} with type '{type_}'")

    rdf_path = Path("main/dist/rdf.yaml")
    rdf_path.parent.mkdir(exist_ok=True)
    yaml.dump(rdf, rdf_path)
    with open(rdf_path.with_suffix(".json"), "w") as f:
        json.dump(rdf, f)

    return 0


if __name__ == "__main__":
    typer.run(main)
