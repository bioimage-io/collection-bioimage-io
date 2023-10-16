import copy
import shutil
from pathlib import Path
from typing import Any, Dict, List

import typer
from bioimageio.spec.shared import yaml
from packaging.version import Version
from utils import iterate_known_resource_versions


def get_sub_summaries(path: Path):
    subs = yaml.load(path)
    if isinstance(subs, dict):  # account for previous single sub summary format
        subs = [subs]

    return [{k: v for k, v in sub.items() if k != "source_name"} for sub in subs]


def filter_test_summaries(tests: Dict[str, List[Dict[str, Any]]]) -> Dict[str, List[Dict[str, Any]]]:
    unique_tests = set()
    ret = {}
    for partner in ["bioimageio"] + [p for p in tests if p != "bioimageio"]:  # process 'bioimageio' first
        for summary in tests.get(partner, []):
            key = tuple(
                [
                    str(summary.get(k))
                    for k in (
                        "bioimageio_spec_version",
                        "bioimageio_core_version",
                        "name",
                        "status",
                        "error",
                        "warnings",
                        "nested_errors",
                    )
                ]
            )
            if key in unique_tests:
                continue

            unique_tests.add(key)
            if partner not in ret:
                ret[partner] = []

            ret[partner].append(summary)

    return ret


def main(
    dist: Path = Path(__file__).parent / "../dist/gh_pages_update",
    collection: Path = Path(__file__).parent / "../collection",
    gh_pages: Path = Path(__file__).parent / "../gh-pages",
    artifact_dir: Path = Path(__file__).parent
    / "../artifacts",  # folder with bioimageio test summary artifacts and updated rdfs
    partner_test_summaries: Path = Path(__file__).parent
    / "../partner_test_summaries",  # folder with partner test summaries
    branch: str = "",
    local: bool = False,  # slightly different paths for dynamic summaries when running locally
):
    dist.mkdir(parents=True, exist_ok=True)
    branch = branch.replace("refs/heads/", "")
    if branch.startswith("auto-update-"):
        resource_id_pattern = branch[len("auto-update-") :]
    else:
        resource_id_pattern = "**"

    # copy updated rdfs to gh_pages/rdfs (to iterate over below) and to dist/rdfs (to be deployed to gh-pages)
    static_validation_artifact_dir = artifact_dir / "static_validation_artifact"
    for updated_rdf_path in static_validation_artifact_dir.glob(f"{resource_id_pattern}/*/rdf.yaml"):
        updated_rdf_gh_pages_path = gh_pages / "rdfs" / updated_rdf_path.relative_to(static_validation_artifact_dir)
        updated_rdf_gh_pages_path.parent.mkdir(exist_ok=True, parents=True)
        print(f"copy to deploy: {updated_rdf_path} -> {updated_rdf_gh_pages_path}")
        shutil.copy(str(updated_rdf_path), str(updated_rdf_gh_pages_path))

        updated_rdf_deploy_path = dist / "rdfs" / updated_rdf_path.relative_to(static_validation_artifact_dir)
        updated_rdf_deploy_path.parent.mkdir(exist_ok=True, parents=True)
        shutil.move(str(updated_rdf_path), str(updated_rdf_deploy_path))

    for krv in iterate_known_resource_versions(
        collection=collection, gh_pages=gh_pages, resource_id=resource_id_pattern, status="accepted"
    ):
        print(f"updating test summary for {krv.resource_id}/{krv.version_id}")
        previous_test_summary_path = gh_pages / "rdfs" / krv.resource_id / krv.version_id / "test_summary.yaml"
        if previous_test_summary_path.exists():
            previous_test_summary = yaml.load(previous_test_summary_path) or {}
        else:
            previous_test_summary = {}

        test_summary = copy.deepcopy(previous_test_summary)
        test_summary["rdf_sha256"] = krv.rdf_sha256
        if "tests" not in test_summary:
            test_summary["tests"] = {}

        # if a static validation summary exists in the artifact, update bioimageio test summaries
        static_validation_summaries = sorted(
            static_validation_artifact_dir.glob(f"{krv.resource_id}/{krv.version_id}/validation_summary_*static.yaml")
        )

        print("static_validation_summaries", static_validation_summaries)
        if static_validation_summaries:
            # reset bioimageio test summaries
            test_summary["tests"]["bioimageio"] = []
            success = True

            # append static validation summaries from artifact
            spec_versions = set()
            for sp in static_validation_summaries:
                for sub_summary in get_sub_summaries(sp):
                    test_summary["tests"]["bioimageio"].append(sub_summary)
                    spec_versions.add(Version(sub_summary["bioimageio_spec_version"]))

                    success &= sub_summary.get("status") == "passed"

            if local:
                dyn_sums = sorted(
                    artifact_dir.glob(
                        f"dynamic_validation_artifact/{krv.resource_id}/{krv.version_id}/*/validation_summary_*.yaml"
                    )
                )
            else:
                dyn_sums = sorted(
                    artifact_dir.glob(
                        f"dynamic_validation_artifact_{krv.resource_id.replace('/', '')}_{krv.version_id.replace('/', '')}_*/validation_summary_*.yaml"
                    )
                )

            print("dyn sums:\n", dyn_sums)
            # append dynamic validation summaries from artifact
            core_versions = set()
            for sp in dyn_sums:
                for sub_summary in get_sub_summaries(sp):
                    test_summary["tests"]["bioimageio"].append(sub_summary)
                    success &= sub_summary.get("status") == "passed"
                    if "bioimageio_core_version" in sub_summary:
                        core_versions.add(Version(sub_summary["bioimageio_core_version"]))

            if spec_versions:
                test_summary["bioimageio_spec_version"] = str(max(spec_versions))

            if core_versions:
                test_summary["bioimageio_core_version"] = str(max(core_versions))

            test_summary["status"] = "passed" if success else "failed"

        # update partner test summaries (blindly)
        #   remove partner test summaries
        test_summary["tests"] = (
            {"bioimageio": test_summary["tests"]["bioimageio"]} if "bioimageio" in test_summary["tests"] else {}
        )

        #   set partner test summaries
        if partner_test_summaries.exists():
            for partner_folder in partner_test_summaries.iterdir():
                assert partner_folder.is_dir()
                partner_id = partner_folder.name
                assert partner_id != "bioimageio"
                test_summary["tests"][partner_id] = []
                for sp in (partner_folder / krv.resource_id / krv.version_id).glob("*test_summary*.yaml"):
                    test_summary["tests"][partner_id] += get_sub_summaries(sp)

        test_summary["tests"] = filter_test_summaries(test_summary["tests"])

        # write updated test summary
        if test_summary != previous_test_summary:
            updated_test_summary_path = dist / previous_test_summary_path.relative_to(gh_pages)
            assert not updated_test_summary_path.exists()
            updated_test_summary_path.parent.mkdir(exist_ok=True, parents=True)
            yaml.dump(test_summary, updated_test_summary_path)


if __name__ == "__main__":
    typer.run(main)
