from pathlib import Path
from typing import List, Optional

import typer

from bioimageio.core.resource_tests import test_resource
from bioimageio.spec.shared import yaml

try:
    from typing import get_args
except ImportError:
    from typing_extensions import get_args  # type: ignore


def main(
    dist: Path,
    resource_id: str,
    version_id: str,
    weight_format: Optional[str] = typer.Argument(..., help="weight format to test model with."),
    rdf_dirs: List[Path] = (Path(__file__).parent / "../gh-pages/rdfs", Path(__file__).parent / "../dist/updated_rdfs/rdfs"),
):
    if weight_format is None:
        # no dynamic tests for non-model resources...
        return

    for root in rdf_dirs:
        rdf_path = root / resource_id / version_id / "rdf.yaml"
        if rdf_path.exists():
            break
    else:
        raise FileNotFoundError(f"{resource_id}/{version_id}/rdf.yaml in {rdf_dirs}")

    summary = test_resource(rdf_path, weight_format=weight_format)
    if "name" not in summary:  # todo: remove, summaries of the future always have a name
        summary["name"] = "reproduced test outputs from test inputs"

    summary_path = dist / resource_id / version_id / weight_format / f"validation_summary_{weight_format}.yaml"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    yaml.dump(summary, summary_path)


if __name__ == "__main__":
    typer.run(main)
