"""script to run a rough equivalent of the github actions workflow 'collection_main.yaml' locally"""
import subprocess
from pathlib import Path
from pprint import pprint

import typer

from dynamic_validation import main as dynamic_validation
from get_pending_validations import main as get_pending_validations
from generate_collection_rdf import main as generate_collection_rdf
from update_known_resources import main as update_known_resources
from deploy_test_summaries import main as deploy_test_summaries
from static_validation import main as static_validation
from utils import iterate_over_gh_matrix


def main(
    collection_dir: Path = Path(__file__).parent / "../collection",
    gh_pages: Path = Path(__file__).parent / "../gh-pages",
    dist: Path = Path(__file__).parent / "../dist",
    artifacts: Path = Path(__file__).parent / "../artifacts",
):
    if not gh_pages.exists():
        subprocess.run(["git", "worktree", "prune"], check=True)
        subprocess.run(["git", "worktree", "add", str(gh_pages), "gh-pages"], check=True)

    updates = update_known_resources(collection_dir=collection_dir)
    print("would open auto-update PRs for:")
    pprint(updates)

    generate_collection_rdf(collection_dir=collection_dir, dist=dist)

    pending = get_pending_validations(collection_dir=collection_dir, gh_pages_dir=gh_pages)

    print("\npending:")
    pprint(pending)

    if not pending["has_pending_matrix"]:
        return

    # perform static validation for pending resources
    static_out = static_validation(dist=artifacts / "static_validation_artifact", pending_matrix=pending["pending_matrix"])
    print("\nstatic validation:")
    pprint(static_out)

    if not static_out["has_dynamic_test_cases"]:
        return

    for matrix in iterate_over_gh_matrix(static_out["dynamic_test_cases"]):
        print(
            f"\ndynamic validation (r: {matrix['resource_id']}, v: {matrix['version_id']}, w: {matrix['weight_format']}):"
        )
        dynamic_validation(
            dist=artifacts / "dynamic_validation_artifacts",
            resource_id=matrix["resource_id"],
            version_id=matrix["version_id"],
            weight_format=matrix["weight_format"],
        )

    deploy_test_summaries(dist=dist, gh_pages_dir=gh_pages, pending_versions=pending["pending_matrix"], artifact_dir=artifacts)

    # CI would rerun generate_collection_rdf here, but we haven't actually deployed any update to gh-pages...


if __name__ == "__main__":
    typer.run(main)
