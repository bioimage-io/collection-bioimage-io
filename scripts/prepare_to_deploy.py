import json
import shutil
import warnings
from pathlib import Path

import typer
from ruamel.yaml import YAML

from bioimageio.spec import load_raw_resource_description
from bioimageio.spec.io_ import serialize_raw_resource_description_to_dict

yaml = YAML(typ="safe")


def main(
    collection_folder: Path,
    branch: str = typer.Argument(
        ..., help="branch name should be 'auto-update-{resource_id} and is only used to get resource_id."
    ),
    resource_folder: Path = typer.Argument(...),
    pending_versions: str = typer.Argument(..., help="json string of list of pending versions_ids"),
    artifact_folder: Path = typer.Argument(..., help="folder with validation artifacts"),
) -> int:
    if branch.startswith("auto-update-"):
        resource_id = branch[len("auto-update-") :]
    else:
        warnings.warn(f"called with non-auto-update branch {branch}")
        return 0

    resource_path = collection_folder / resource_id / "resource.yaml"
    resource = yaml.load(resource_path)

    pending_versions = json.loads(pending_versions)
    for v in resource["versions"]:
        version_id = v["version_id"]
        if version_id not in pending_versions or v["status"] == "blocked":
            continue

        rdf_node = load_raw_resource_description(v["source"])
        rdf_data = serialize_raw_resource_description_to_dict(rdf_node)
        rdf_data.update(v)

        yaml.dump(rdf_data, resource_folder / version_id / "rdf.yaml")

        # move validation summaries and conda env yaml files from artifact to version_id folder
        for sp in artifact_folder.glob(f"{version_id.replace('/', '')}*/**/*.yaml"):
            shutil.move(sp, resource_folder / version_id)

    return 0


if __name__ == "__main__":
    typer.run(main)
