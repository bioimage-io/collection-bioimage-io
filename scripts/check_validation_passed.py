from pathlib import Path
from pprint import pprint

import typer

from bioimageio.spec.shared import yaml


def main(
    artifact_dir: Path = typer.Argument(..., help="folder with validation artifacts")
):
    # check validation summaries in artifact folder
    failed_val = {}
    for sp in artifact_dir.glob(f"**/validation_summary*.yaml"):
        summary = yaml.load(sp)
        if summary["error"]:
            failed_val[sp.stem] = summary

    if failed_val:
        pprint(failed_val, width=120)
        raise typer.Exit(code=1)


if __name__ == "__main__":
    typer.run(main)
