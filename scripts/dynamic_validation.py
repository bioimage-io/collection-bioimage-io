from pathlib import Path

import typer

from bioimageio.core.resource_tests import test_resource
from bioimageio.spec.shared import yaml

from typing import Optional

try:
    from typing import get_args
except ImportError:
    from typing_extensions import get_args  # type: ignore

SOURCE_BASE_URL = "https://bioimage-io.github.io/collection-bioimage-io"


def main(
    dist: Path,
    resource_id: str,
    version_id: str,
    weight_format: Optional[str] = typer.Argument(None, help="weight format to test model with."),
):
    if weight_format is None:
        # no dynamic tests for non-model resources...
        return

    summary_path = dist / resource_id / version_id / weight_format / f"validation_summary_{weight_format}.yaml"
    rdf_source = f"{SOURCE_BASE_URL}/resources/{resource_id}/{version_id}/rdf.yaml"

    summary = test_resource(rdf_source, weight_format=weight_format)
    if "name" not in summary:  # todo: remove, summaries of the future always have a name
        summary["name"] = "reproduced test outputs from test inputs"

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    yaml.dump(summary, summary_path)


if __name__ == "__main__":
    typer.run(main)
