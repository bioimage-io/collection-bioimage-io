"""script to run a rough equivalent of the github actions workflow 'auto_update_pr.yaml' locally"""
import subprocess
from pathlib import Path
from pprint import pprint

import typer

from get_pending import main as get_pending
from static_validation import main as static_validation
from utils import iterate_over_gh_marix


def main(
    resource_id: str,
    collection: Path = Path(__file__).parent / "../collection",
    gh_pages: Path = Path(__file__).parent / "../gh-pages",
):
    if not gh_pages.exists():
        subprocess.run(["git", "worktree", "add", str(gh_pages), "gh-pages"])

    branch = f"auto-update-{resource_id}"
    pending = get_pending(collection_folder=collection, branch=branch)
    print("\npending:")
    pprint(pending)

    # perform static validation for pending resources
    resource_folder = gh_pages / "resources"
    for matrix in iterate_over_gh_marix(pending["pending_matrix"]):
        assert pending["found_pending"]
        static_out = static_validation(
            collection_folder=collection,
            branch=branch,
            resource_folder=resource_folder,
            version_id=matrix["version_id"],
        )
        print("\nstatic validation:")
        pprint(static_out)



if __name__ == "__main__":
    typer.run(main)
