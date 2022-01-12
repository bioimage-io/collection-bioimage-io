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
    collection_dir: Path,
    resources_dir: Path,
    resource_id: str,
    version_id: str,
    weight_format: Optional[str] = typer.Argument(None, help="weight format to test model with."),
):
    if weight_format is None:
        # no dynamic tests for non-model resources...
        return

    summary_path = resources_dir / resource_id / version_id / weight_format / f"validation_summary_{weight_format}.yaml"

    resource_path = collection_dir / resource_id / "resource.yaml"
    if resource_path.exists():
        # resource from collection folder
        resource_versions = [v for v in yaml.load(resource_path)["versions"] if v["version_id"] == version_id]
        assert len(resource_versions) == 1
        resource_version = resource_versions[0]
        source = resource_version["source"]
    else:
        # resource from partner
        source = resource_path / resource_id / version_id

    summary = test_resource(source, weight_format=weight_format)
    summary["name"] = "reproduced test outputs"

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    yaml.dump(summary, summary_path)


if __name__ == "__main__":
    typer.run(main)
