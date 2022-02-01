from pathlib import Path
from pprint import pprint

import typer
from ruamel.yaml import YAML

yaml = YAML(typ="safe")


def main(
    artifact_dir: Path = typer.Argument(..., help="folder with validation artifacts")
):
    # check validation summaries in artifact folder
    failed_val = []
    for sp in artifact_dir.glob(f"**/validation_summary*.yaml"):
        summary = yaml.load(sp)
        if summary["error"]:
            summary["id"] = sp.stem
            failed_val.append(summary)

    if failed_val:
        pprint(failed_val)
        raise typer.Exit(code=1)


if __name__ == "__main__":
    typer.run(main)
