"""script to run a rough equivalent of the github actions workflow 'collection_main.yaml' locally"""
import shutil
import subprocess
from pathlib import Path
from pprint import pprint

import typer

from deploy_test_summaries import main as deploy_test_summaries_script
from dynamic_validation import main as dynamic_validation_script
from generate_collection_rdf import main as generate_collection_rdf_script
from get_pending_validations import main as get_pending_validations_script
from static_validation import main as static_validation_script
from update_external_resources import main as update_external_resources_script
from update_partner_resources import main as update_partner_resources_script
from update_resource_rdfs import main as update_resource_rdfs_script
from utils import iterate_over_gh_matrix


def fake_deploy(dist: Path, deploy_to: Path):
    shutil.copytree(str(dist), str(deploy_to), dirs_exist_ok=True)
    shutil.rmtree(str(dist))


def end_of_step(always_continue: bool):
    if not always_continue and input("Continue?([y]/n)").lower().startswith("n"):
        raise RuntimeError("abort")


def main(
    collection_dir: Path = Path(__file__).parent / "../collection",
    gh_pages: Path = Path(__file__).parent / "../gh-pages",
    dist: Path = Path(__file__).parent / "../dist",
    artifacts: Path = Path(__file__).parent / "../artifacts",
    rdf_template_path: Path = Path(__file__).parent / "../collection_rdf_template.yaml",
    current_collection_format: str = "0.2.2",
    always_continue: bool = True,
):
    if not gh_pages.exists():
        subprocess.run(["git", "worktree", "prune"], check=True)
        subprocess.run(["git", "worktree", "add", "--detach", str(gh_pages), "gh-pages"], check=True)

    ##################
    # update resources
    ##################
    update_partner_resources_script(
        dist=dist,
        gh_pages=gh_pages,
        rdf_template_path=rdf_template_path,
        current_collection_format=current_collection_format,
    )
    fake_deploy(dist, gh_pages)

    updates = update_external_resources_script(collection_dir=collection_dir)
    print("would open auto-update PRs with:")
    pprint(updates)

    fake_deploy(dist, collection_dir)

    end_of_step(always_continue)
    #########################
    # get pending validations
    #########################
    pending = get_pending_validations_script(collection_dir=collection_dir, gh_pages_dir=gh_pages)

    print("\npending:")
    pprint(pending)

    if not pending["has_pending_matrix"]:
        return

    # create updated rdfs that don't exist yet
    pending = update_resource_rdfs_script(
        dist=dist,
        pending_matrix=pending["pending_matrix"],
        collection_dir=collection_dir,
        future_deployed_path=gh_pages,
    )

    print("\npending (updated):")
    pprint(pending)

    fake_deploy(dist, gh_pages)

    end_of_step(always_continue)
    ############################
    # validate/static-validation
    ############################
    # perform static validation for pending resources
    static_out = static_validation_script(
        dist=artifacts / "static_validation_artifact", pending_matrix=pending["pending_matrix"]
    )
    print("\nstatic validation:")
    pprint(static_out)

    if not static_out["has_dynamic_test_cases"]:
        return

    end_of_step(always_continue)
    #############################
    # validate/dynamic-validation
    #############################
    for matrix in iterate_over_gh_matrix(static_out["dynamic_test_cases"]):
        print(
            f"\ndynamic validation (r: {matrix['resource_id']}, v: {matrix['version_id']}, w: {matrix['weight_format']}):"
        )
        dynamic_validation_script(
            dist=artifacts / "dynamic_validation_artifacts",
            resource_id=matrix["resource_id"],
            version_id=matrix["version_id"],
            rdf_path=matrix["rdf_path"],
            weight_format=matrix["weight_format"],
        )

    end_of_step(always_continue)
    #################
    # validate/deploy
    #################
    deploy_test_summaries_script(
        dist=dist, gh_pages_dir=gh_pages, pending_versions=pending["pending_matrix"], artifact_dir=artifacts
    )

    fake_deploy(dist, gh_pages)

    end_of_step(always_continue)
    ##################
    # build-collection
    ##################
    generate_collection_rdf_script(collection_dir=collection_dir, dist=dist)

    fake_deploy(dist, gh_pages)


if __name__ == "__main__":
    typer.run(main)
