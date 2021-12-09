from pathlib import Path

import typer

from bioimageio.core.resource_tests import test_resource
from bioimageio.spec import validate
from bioimageio.spec.shared import yaml

try:
    from typing import Optional, get_args
except ImportError:
    from typing_extensions import get_args  # type: ignore


def main(
    summary_root: Path,
    doi: str,
    weight_format: Optional[str] = typer.Argument(None, help="weight format to test model with."),
) -> int:
    summary_name = "validation_summary.yaml"
    if weight_format is not None:
        summary_name = f"{weight_format}_{summary_name }"

    summary_path = summary_root / doi / summary_name
    assert not summary_path.exists()

    NAME = "name"
    ERROR = "error"
    SUCCESS = "success"
    NESTED_ERRORS = "nested_errors"
    TRACEBACK = "traceback"

    s = validate(doi)
    static_error = s.get(ERROR, None)
    static_nested_errors = s.get(NESTED_ERRORS, None)
    static_check = {NAME: "static resource format validation", SUCCESS: not (static_error or static_nested_errors)}
    if not static_check[SUCCESS]:
        static_check[ERROR] = static_error
        static_check[TRACEBACK] = s.get(TRACEBACK, None)
        static_check[NESTED_ERRORS] = static_nested_errors

    dynamic_check = {NAME: "reproduced test outputs"}
    if static_error is None:
        # dynamic test
        dyn_summary = test_resource(doi, weight_format=weight_format)
        dyn_error = dyn_summary.get(ERROR, None)
        dynamic_check[SUCCESS] = dyn_error is None
        if not dynamic_check[SUCCESS]:
            dynamic_check[ERROR] = dyn_error
            dynamic_check[TRACEBACK] = dyn_summary.get(TRACEBACK, None)
    else:
        dynamic_check[SUCCESS] = False
        dynamic_check[ERROR] = "skipped due to invalid resource format"
        dynamic_check[TRACEBACK] = None

    summary = {"static": static_check, "dynamic": dynamic_check}

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    yaml.dump(summary, summary_path)
    return 0


if __name__ == "__main__":
    typer.run(main)
