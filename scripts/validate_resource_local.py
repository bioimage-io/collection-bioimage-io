"""script to run a rough equivalent of the github actions workflow 'auto_update_pr.yaml' locally"""
import subprocess
from pathlib import Path
from pprint import pprint

import typer

from dynamic_validation import main as dynamic_validation
from get_pending import main as get_pending
from get_pending_validations import main as get_pending_validations
from static_validation import main as static_validation
from utils import iterate_over_gh_matrix


def main(
    resource_id: str = "all_pending",
    collection_dir: Path = Path(__file__).parent / "../collection",
    gh_pages: Path = Path(__file__).parent / "../gh-pages",
):
    if not gh_pages.exists():
        subprocess.run(["git", "worktree", "add", str(gh_pages), "gh-pages"])

    if resource_id == "all_pending":
        pending = get_pending_validations(collection_dir=collection_dir, gh_pages_dir=gh_pages)
    else:
        branch = f"auto-update-{resource_id}"
        pending = get_pending(collection_dir=collection_dir, branch=branch)

    print("\npending:")
    pprint(pending)

    if not pending["has_pending_matrix"]:
        return

    # perform static validation for pending resources
    resources_dir = gh_pages / "resources"
    static_out = static_validation(
        collection_dir=collection_dir, resources_dir=resources_dir, pending_matrix=pending["pending_matrix"]
    )
    print("\nstatic validation:")
    pprint(static_out)

    if not static_out["has_dynamic_test_cases"]:
        return

    for matrix in iterate_over_gh_matrix(static_out["dynamic_test_cases"]):
        print(f"\ndynamic validation (r: {matrix['resource_id']}, v: {matrix['version_id']}):")
        dynamic_validation(
            collection_dir=collection_dir,
            resources_dir=resources_dir,
            resource_id=matrix["resource_id"],
            version_id=matrix["version_id"],
            weight_format=matrix["weight_format"],
        )


if __name__ == "__main__":
    typer.run(main)
