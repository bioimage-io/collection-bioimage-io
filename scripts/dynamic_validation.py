import traceback
from pathlib import Path
from typing import List, Optional

import typer

from bioimageio.spec.shared import yaml


def main(
    dist: Path,
    resource_id: str,
    version_id: str,
    weight_format: Optional[str] = typer.Argument(..., help="weight format to test model with."),
    rdf_dirs: List[Path] = (Path(__file__).parent / "../dist/static_validation_artifact",),
    create_env_outcome: str = "success",
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

    if create_env_outcome == "success":
        try:
            from bioimageio.core.resource_tests import test_resource
        except Exception as e:
            summary = dict(
                name="import test_resource from test environment",
                status="failed",
                error=str(e),
                traceback=traceback.format_tb(e.__traceback__),
            )
        else:
            summary = test_resource(rdf_path, weight_format=weight_format)
            if "name" not in summary:  # todo: remove, summaries of the future always have a name
                summary["name"] = "reproduced test outputs from test inputs"
    else:
        env_path = dist / "static_validation_artifact" / resource_id / version_id / f"conda_env_{weight_format}.yaml"
        if env_path.exists():
            error = "Failed to install conda environment:\n" + env_path.read_text()
        else:
            error = f"Conda environment yaml file not found: {env_path}"

        summary = dict(name="install test environment", status="failed", error=error)

    summary_path = dist / resource_id / version_id / weight_format / f"validation_summary_{weight_format}.yaml"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    yaml.dump(summary, summary_path)


if __name__ == "__main__":
    typer.run(main)
