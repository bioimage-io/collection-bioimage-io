from pathlib import Path

import typer

from bioimageio.core.resource_tests import test_resource
from bioimageio.spec.shared import yaml

from typing import Optional

try:
    from typing import get_args
except ImportError:
    from typing_extensions import get_args  # type: ignore


def main(
    collection_folder: Path,
    resources_folder: Path,
    resource_id: str,
    version_id: str,
    weight_format: Optional[str] = typer.Argument(None, help="weight format to test model with."),
):
    if weight_format is None:
        # no dynamic tests for non-model resources...
        return

    summary_path = resources_folder / resource_id / version_id / weight_format / f"validation_summary_{weight_format}.yaml"

    resource_versions = [
        v
        for v in yaml.load(collection_folder / resource_id / "resource.yaml")["versions"]
        if v["version_id"] == version_id
    ]
    assert len(resource_versions) == 1
    resource_version = resource_versions[0]
    source = resource_version["source"]

    summary = test_resource(source, weight_format=weight_format)
    summary["name"] = "reproduced test outputs"

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    yaml.dump(summary, summary_path)


if __name__ == "__main__":
    typer.run(main)
