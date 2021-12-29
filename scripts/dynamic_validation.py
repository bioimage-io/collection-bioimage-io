from pathlib import Path

import typer

from bioimageio.core.resource_tests import test_resource
from bioimageio.spec.shared import yaml

try:
    from typing import Optional, get_args
except ImportError:
    from typing_extensions import get_args  # type: ignore


def main(
    collection_folder: Path,
    branch: str,
    resource_folder: Path,
    version_id: str,
    weight_format: Optional[str] = typer.Argument(
        None, help="weight format to test model with."
    ),
) -> int:
    if branch.startswith("auto-update-"):
        resource_id = branch[len("auto-update-") :]
    else:
        print(f"called with non-auto-update branch {branch}")
        return 0

    if weight_format is None:
        # no dynamic tests for non-model resources...
        return 0

    summary_path = (
        resource_folder
        / version_id
        / weight_format
        / f"validation_summary_{weight_format}.yaml"
    )

    resoruce_versions = [
        v
        for v in yaml.load(collection_folder / resource_id / "resource.yaml")[
            "versions"
        ]
        if v["version_id"] == version_id
    ]
    assert len(resoruce_versions) == 1
    resource_version = resoruce_versions[0]
    source = resource_version["source"]

    summary = test_resource(source, weight_format=weight_format)
    summary["name"] = "reproduced test outputs"

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    yaml.dump(summary, summary_path)
    return 0


if __name__ == "__main__":
    typer.run(main)
