import shutil
from pathlib import Path

import typer
from ruamel.yaml import YAML

from utils import iterate_over_gh_matrix

yaml = YAML(typ="safe")


def main(
    resources_dir: Path = typer.Argument(...),
    pending_versions: str = typer.Argument(..., help="json string of list of pending versions_ids"),
    artifact_dir: Path = typer.Argument(..., help="folder with validation and conda environment artifacts"),
):
    for matrix in iterate_over_gh_matrix(pending_versions):
        resource_id = matrix["resource_id"]
        version_id = matrix["version_id"]

        # move validation summaries and conda env yaml files from artifact to version_id folder
        version_folder = resources_dir / resource_id / version_id
        version_folder.mkdir(parents=True, exist_ok=True)
        for sp in artifact_dir.glob(f"**/{resource_id.replace('/', '')}{version_id.replace('/', '')}*/**/*.yaml"):
            shutil.move(str(sp), str(version_folder))


if __name__ == "__main__":
    typer.run(main)
