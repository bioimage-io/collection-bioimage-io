import json
import sys
import warnings
from argparse import ArgumentParser
from pathlib import Path

from ruamel.yaml import YAML

yaml = YAML(typ="safe")

try:
    from typing import get_args
except ImportError:
    from typing_extensions import get_args  # type: ignore

try:
    from bioimageio import core
except ImportError:
    core = None


def parse_args():
    p = ArgumentParser(description="Combine a group of summary files to the final summary files per model")
    p.add_argument("summaries_dir", type=Path)
    p.add_argument("output_dir", type=Path, help="path where to write validation summary to")

    args = p.parse_args()
    return args


def main(summaries_dir: Path, output_dir: Path) -> int:
    # summaries_dir has a subdir per env
    all_summaries = [(p.parent.name, yaml.load(p)) for p in summaries_dir.glob("*/*.yaml")]
    assert all(isinstance(s, dict) for en, s in all_summaries)

    # gather all dois across test environments
    all_dois = set.union(*[set(s.keys()) for en, s in all_summaries])
    env_names = {en for en, s in all_summaries}

    for doi in all_dois:
        final_summary = {}
        for env_name, summaries in all_summaries:
            if doi not in summaries:
                continue

            summary = summaries[doi]
            assert "name" in summary
            assert "source_name" in summary
            assert "static_error" in summary
            assert "static_traceback" in summary
            assert "static_nested_errors" in summary
            assert "dynamic_tests" in summary
            assert isinstance(summary["dynamic_tests"], dict)

            if env_name not in final_summary:
                # start final summary from the first summary encountered for this doi and env
                final_summary[env_name] = summary
            else:

                def inconsistent_static_report_warning(key, v1, v2):
                    return (
                        f"expected all dynamic tests to report the same {key}, "
                        f"but for doi {doi} in test env {env_name} we got '{v1}' and '{v2}'"
                    )

                # warn about inconsistent static reports in summary
                for static_key in ("name", "source_name", "static_error", "static_traceback", "static_nested_errors"):
                    if final_summary[env_name][static_key] != summary[static_key]:
                        warnings.warn(
                            inconsistent_static_report_warning(
                                static_key, final_summary[env_name][static_key], summary[static_key]
                            )
                        )

                # add dynamic test report(s) to final summary
                for test_name, report in summary["dynamic_tests"].items():
                    if test_name in final_summary[env_name]["dynamic_tests"]:
                        warnings.warn(f"Overwriting dynamic test {test_name} for doi {doi} in test env {env_name}")

                    final_summary[env_name]["dynamic_tests"].update()

        out_path = output_dir / f"{doi}.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)  # doi has slashes that create subdirs
        with out_path.open("w") as f:
            json.dump(final_summary, f, indent=2, sort_keys=True)

    return 0


if __name__ == "__main__":
    args = parse_args()
    sys.exit(main(args.summaries_dir, args.output_dir))
