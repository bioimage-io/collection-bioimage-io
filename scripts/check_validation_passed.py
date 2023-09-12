import os
from pathlib import Path
from pprint import pprint

import typer

from bioimageio.spec.shared import yaml


def main(artifact_dir: Path = typer.Argument(..., help="folder with validation artifacts")):
    """check validation summaries in artifact folder"""
    failed_val = []
    for sp in sorted(artifact_dir.glob("**/validation_summary*.yaml"), key=os.path.getmtime):
        summary = yaml.load(sp)
        if isinstance(summary, dict):
            summary = [summary]

        for s in summary:
            if s["status"] != "passed":
                s["id"] = sp.stem
                failed_val.append(summary)

    if failed_val:
        pprint(failed_val, width=120)
        raise typer.Exit(code=1)


if __name__ == "__main__":
    typer.run(main)
