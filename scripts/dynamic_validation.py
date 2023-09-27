import traceback
from functools import partialmethod
from pathlib import Path
from typing import List, Optional, Sequence

import typer
from bioimageio.spec import load_raw_resource_description
from bioimageio.spec.shared import yaml
from marshmallow import missing
from tqdm import tqdm

tqdm.__init__ = partialmethod(tqdm.__init__, disable=True)  # silence tqdm


def test_summary_from_exception(name, exception):
    return dict(
        name=name, status="failed", error=str(exception), traceback=traceback.format_tb(exception.__traceback__)
    )


def main(
    dist: Path,
    resource_id: str,
    version_id: str,
    weight_format: Optional[str] = typer.Argument(..., help="weight format to test model with."),
    rdf_dirs: Sequence[Path] = (Path(__file__).parent / "../artifacts/static_validation_artifact",),
    create_env_outcome: str = "success",
    # rdf_source might assume a resource has been deployed, if not (e.g. in a PR), rdf_source is expected to be invalid.
    ignore_rdf_source_field_in_validation: bool = False,
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
            summary = test_summary_from_exception("import test_resource from test environment", e)
        else:
            try:
                rdf = yaml.load(rdf_path)
                test_kwargs = rdf.get("config", {}).get("bioimageio", {}).get("test_kwargs", {}).get(weight_format, {})
            except Exception as e:
                summary = test_summary_from_exception("check for test kwargs", e)
            else:
                try:
                    rd = load_raw_resource_description(rdf_path)
                    if ignore_rdf_source_field_in_validation:
                        rd.rdf_source = missing

                    summary = test_resource(rd, weight_format=weight_format, **test_kwargs)
                except Exception as e:
                    summary = test_summary_from_exception("call 'test_resource'", e)

    else:
        env_path = root / resource_id / version_id / f"conda_env_{weight_format}.yaml"
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
