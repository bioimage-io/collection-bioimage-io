from pathlib import Path
from pprint import pprint

import typer
from ruamel.yaml import YAML

yaml = YAML(typ="safe")


def main(artifact_folder: Path = typer.Argument(..., help="folder with validation artifacts")):
    # check validation summaries in artifact folder
    failed_val = []
    for sp in artifact_folder.glob(f"**/validation_summary*.yaml"):
        summary = yaml.load(sp)
        if summary["error"]:
            failed_val.append(summary)

    if failed_val:
        pprint(failed_val)
        raise typer.Exit(code=1)


if __name__ == "__main__":
    typer.run(main)
