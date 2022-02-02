import warnings
from pathlib import Path

import typer

from bioimageio.spec.shared import yaml
from utils import iterate_over_gh_matrix


def reset_test_summary_in_rdf(rdf: dict):
    rdf["config"] = rdf.get("config", {})
    rdf["config"]["bioimageio"] = rdf["config"].get("bioimageio", {})
    rdf["config"]["bioimageio"]["test_summary"] = test_summary = rdf["config"]["bioimageio"].get("test_summary", {})
    test_summary["tests"] = []
    test_summary["status"] = "pending"


def add_test_summary_to_rdf(rdf: dict, summary_path: Path):
    new_summary = yaml.load(summary_path)
    test_summary = rdf["config"]["bioimageio"]["test_summary"]
    if test_summary["status"] == "pending":
        test_summary["status"] = "passed"

    if new_summary["error"] is not None:
        test_summary["status"] = "failed"

    test_summary["tests"].append({k: v for k, v in new_summary.items() if k != "source_name"})
    print(f"\tadded {new_summary['name']} to test_summary")


def main(
    dist: Path,
    pending_versions: str = typer.Argument(..., help="json string of list of pending versions_ids"),
    artifact_dir: Path = typer.Argument(..., help="folder with validation and conda environment artifacts"),
):
    for matrix in iterate_over_gh_matrix(pending_versions):
        resource_id = matrix["resource_id"]
        version_id = matrix["version_id"]
        rdf_path = Path(matrix["rdf_path"])
        assert rdf_path.exists()

        rdf = yaml.load(rdf_path)
        reset_test_summary_in_rdf(rdf)

        print(f"insert test summaries for {resource_id}/{version_id}")
        # insert static validation summaries from artifact into rdf
        for sp in sorted(
            artifact_dir.glob(f"static_validation_artifact/{resource_id}/{version_id}/validation_summary_*static.yaml")
        ):
            add_test_summary_to_rdf(rdf, sp)

        # insert dynamic validation summaries from artifact into rdf
        for sp in sorted(
            artifact_dir.glob(
                f"dynamic_validation_artifact_{resource_id.replace('/', '')}{version_id.replace('/', '')}*/**/validation_summary_*.yaml"
            )
        ):
            add_test_summary_to_rdf(rdf, sp)

        # write updated rdf
        dist_rdf_path = dist / "rdfs" / resource_id / version_id / "rdf.yaml"
        assert not dist_rdf_path.exists()
        dist_rdf_path.parent.mkdir(exist_ok=True, parents=True)
        yaml.dump(rdf, dist_rdf_path)


if __name__ == "__main__":
    typer.run(main)
