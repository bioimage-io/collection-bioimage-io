import shutil
from pathlib import Path
from typing import Optional

import typer

from bioimageio.spec.shared import yaml
from utils import iterate_known_resource_versions


def get_sub_summary(path: Path):
    sub = yaml.load(path)
    return {k: v for k, v in sub.items() if k != "source_name"}


def main(
    dist: Path,
    collection: Path = Path(__file__).parent / "../collection",
    gh_pages: Path = Path(__file__).parent / "../gh-pages",
    artifact_dir: Path = Path(__file__).parent / "../artifacts",  # folder with bioimageio test summary artifacts
    partner_test_summaries: Path = Path(__file__).parent
    / "../partner_test_summaries",  # folder with partner test summaries
    branch: Optional[str] = None,
):
    dist.mkdir(parents=True, exist_ok=True)
    if branch is not None and branch.startswith("auto-update-"):
        resource_id_pattern = branch[len("auto-update-") :]
    else:
        resource_id_pattern = "**"

    for krv in iterate_known_resource_versions(
        collection=collection, gh_pages=gh_pages, resource_id=resource_id_pattern, status="accepted"
    ):
        static_validation_artifact_dir = artifact_dir / "static_validation_artifact"
        updated_rdf_path = static_validation_artifact_dir / krv.resource_id / krv.version_id / "rdf.yaml"
        if updated_rdf_path.exists():
            # write updated rdf to dist
            updated_rdf_deploy_path = dist / updated_rdf_path.relative_to(static_validation_artifact_dir)
            updated_rdf_deploy_path.parent.mkdir(exist_ok=True, parents=True)
            shutil.copy(str(updated_rdf_path), str(updated_rdf_deploy_path))

        print(f"updating test summary for {krv.resource_id}/{krv.version_id}")
        previous_test_summary_path = gh_pages / "rdfs" / krv.resource_id / krv.version_id / "test_summary.yaml"
        if previous_test_summary_path.exists():
            previous_test_summary = yaml.load(previous_test_summary_path).items()
        else:
            previous_test_summary = {}

        test_summary = dict(previous_test_summary)
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
                sub_summary = get_sub_summary(sp)
                test_summary["tests"]["bioimageio"].append(sub_summary)
                spec_versions.add(sub_summary.get("bioimageio_spec_version"))
                success &= sub_summary.get("status") == "passed"

            print(
                "dyn sums",
                sorted(
                    artifact_dir.glob(
                        f"dynamic_validation_artifact_{krv.resource_id.replace('/', '')}{krv.version_id.replace('/', '')}*/**/validation_summary_*.yaml"
                    )
                ),
            )
            # append dynamic validation summaries from artifact
            core_versions = set()
            for sp in sorted(
                artifact_dir.glob(
                    f"dynamic_validation_artifact_{krv.resource_id.replace('/', '')}{krv.version_id.replace('/', '')}*/**/validation_summary_*.yaml"
                )
            ):
                sub_summary = get_sub_summary(sp)
                test_summary["tests"]["bioimageio"].append(sub_summary)
                # spec_versions.add(sub_summary.get("bioimageio_spec_version"))  # may be behind due to pending core release
                core_versions.add(sub_summary.get("bioimageio_core_version"))
                success &= sub_summary.get("status") == "passed"

            if len(spec_versions) == 1:
                test_summary["bioimageio_spec_version"] = spec_versions.pop()
            elif len(spec_versions) > 1:
                raise RuntimeError(spec_versions)

            if len(core_versions) == 1:
                test_summary["bioimageio_core_version"] = core_versions.pop()
            elif len(core_versions) > 1:
                raise RuntimeError(core_versions)

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
                    test_summary["tests"][partner_id].append(get_sub_summary(sp))

        # write updated test summary
        if test_summary != previous_test_summary:
            updated_test_summary_path = dist / previous_test_summary_path.relative_to(gh_pages)
            assert not updated_test_summary_path.exists()
            updated_test_summary_path.parent.mkdir(exist_ok=True, parents=True)
            yaml.dump(test_summary, updated_test_summary_path)


if __name__ == "__main__":
    typer.run(main)
