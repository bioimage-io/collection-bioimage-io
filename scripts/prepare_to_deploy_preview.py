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

        # move static validation summaries to resource_dir
        resources_dir.mkdir(parents=True, exist_ok=True)
        for sp in artifact_dir.glob(f"static_validation_artifact/**/*.yaml"):
            tgt_subdirs = []
            tgt_part = Path(sp.parent)
            while tgt_part != tgt_part.parent and tgt_part.name != "static_validation_artifact":
                tgt_subdirs.append(tgt_part.name)
                tgt_part = tgt_part.parent

            tgt = Path(resources_dir)
            for subdir in tgt_subdirs[::-1]:
                tgt /= subdir

            tgt.mkdir(parents=True, exist_ok=True)
            shutil.move(str(sp), str(tgt))
            print('moved', tgt / sp.name)

        # move dynamic validation summaries and conda env yaml files from artifact to version_id folder
        version_folder = resources_dir / resource_id / version_id
        version_folder.mkdir(parents=True, exist_ok=True)
        for sp in artifact_dir.glob(f"**/{resource_id.replace('/', '')}{version_id.replace('/', '')}*/**/*.yaml"):
            shutil.move(str(sp), str(version_folder))
            print('moved', version_folder / sp.name)


if __name__ == "__main__":
    typer.run(main)
