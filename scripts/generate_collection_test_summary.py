import platform
import sys
from argparse import ArgumentParser
from pathlib import Path

from bioimageio.core.resource_tests import test_resource
from bioimageio.spec import validate
from bioimageio.spec.model.raw_nodes import WeightsFormat
from bioimageio.spec.shared import yaml

try:
    from typing import get_args
except ImportError:
    from typing_extensions import get_args  # type: ignore

try:
    from bioimageio import core
except ImportError:
    core = None


def parse_args():
    p = ArgumentParser(description="Generate validation summary for a BioImage.IO resource collection")
    p.add_argument("collection_path", type=Path)
    p.add_argument("output_summary_path", type=Path, help="path where to write validation summary to")
    p.add_argument("weights_format", type=str, choices=get_args(WeightsFormat), help="weights format to test with")

    args = p.parse_args()
    return args


def get_model_rersources(collection_path: Path):
    collection = yaml.load(collection_path)
    return {entry["id"]: entry["source"] for entry in collection["attachments"].get("model", {})}


def main(collection_path: Path, output_summary_path: Path, weights_format: WeightsFormat) -> int:
    test_name = f"py{platform.python_version()}_{weights_format}"
    NAME = "name"
    ERROR = "error"
    SUCCESS = "success"
    NESTED_ERRORS = "nested_errors"
    TRACEBACK = "traceback"
    output_summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary = {}
    for id_, source in get_model_rersources(collection_path).items():
        s = validate(source)
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
            dyn_summary = test_resource(source, weight_format=weights_format)
            dyn_error = dyn_summary.get(ERROR, None)
            dynamic_check[SUCCESS] = dyn_error is None
            if not dynamic_check[SUCCESS]:
                dynamic_check[ERROR] = dyn_error
                dynamic_check[TRACEBACK] = dyn_summary.get(TRACEBACK, None)
        else:
            dynamic_check[SUCCESS] = False
            dynamic_check[ERROR] = "skipped due to invalid resource format"
            dynamic_check[TRACEBACK] = None

        summary[id_] = {test_name: [static_check, dynamic_check]}

    yaml.dump(summary, output_summary_path)
    return 0


if __name__ == "__main__":
    args = parse_args()
    sys.exit(main(args.collection_path, args.output_summary_path, args.weights_format))
