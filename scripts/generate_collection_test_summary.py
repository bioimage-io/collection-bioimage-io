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


def get_zenodo_community_rersources(collection_path: Path):
    collection = yaml.load(collection_path)
    return {entry["id"]: entry["source"] for entry in collection["attachments"]["zenodo"]}


def main(collection_path: Path, output_summary_path: Path, weights_format: WeightsFormat) -> int:
    output_summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary = {}
    for id_, source in get_zenodo_community_rersources(collection_path).items():
        s = validate(source)
        assert set(s.keys()) == {"name", "source_name", "error", "traceback", "nested_errors"}, s.keys()
        # prefix static validation summary keys with 'static_'
        s = {k if k in ("name", "source_name") else "static_" + k: v for k, v in s.items()}

        s["dynamic_tests"] = {}
        if s["static_error"] is None:
            # dynamic test
            dyn_summary = test_resource(source, weight_format=weights_format)
            s["dynamic_tests"][f"py{platform.python_version()}_{weights_format}"] = dyn_summary

        summary[id_] = s

    yaml.dump(summary, output_summary_path)
    return 0


if __name__ == "__main__":
    args = parse_args()
    sys.exit(main(args.collection_path, args.output_summary_path, args.weights_format))
