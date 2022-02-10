"""script to run a rough equivalent of the github actions workflow 'collection_main.yaml' locally"""
import json
import shutil
import subprocess
from pathlib import Path
from pprint import pprint

import typer

from deploy_test_summaries import main as deploy_test_summaries_script
from dynamic_validation import main as dynamic_validation_script
from generate_collection_rdf import main as generate_collection_rdf_script
from static_validation import main as static_validation_script
from update_external_resources import main as update_external_resources_script
from update_partner_resources import main as update_partner_resources_script
from update_rdfs import main as update_rdfs_script
from utils import iterate_over_gh_matrix


def fake_deploy(dist: Path, deploy_to: Path):
    if dist.exists():
        shutil.copytree(str(dist), str(deploy_to), dirs_exist_ok=True)
        shutil.rmtree(str(dist))


def end_of_step(always_continue: bool):
    if not always_continue and input("Continue?([y]/n)").lower().startswith("n"):
        raise RuntimeError("abort")


def main(
    collection: Path = Path(__file__).parent / "../collection",
    last_collection: Path = Path(__file__).parent / "../last_ci_run/collection",
    gh_pages: Path = Path(__file__).parent / "../gh-pages",
    dist: Path = Path(__file__).parent / "../dist",
    artifacts: Path = Path(__file__).parent / "../artifacts",
    partner_test_summaries: Path = Path(__file__).parent / "../partner_test_summaries",
    rdf_template_path: Path = Path(__file__).parent / "../collection_rdf_template.yaml",
    current_collection_format: str = "0.2.2",
    always_continue: bool = True,
):
    # local setup
    if not partner_test_summaries.exists():
        partner_test_summaries.mkdir(parents=True)
        # todo: download partner_test_summaries

    if not gh_pages.exists():
        subprocess.run(["git", "worktree", "prune"], check=True)
        subprocess.run(["git", "worktree", "add", "--detach", str(gh_pages), "gh-pages"], check=True)

    if not last_collection.exists():
        subprocess.run(["git", "worktree", "prune"], check=True)
        subprocess.run(["git", "worktree", "add", "--detach", str(last_collection), "last_collection"], check=True)

    ###################################
    # update resources (resource infos)
    ###################################
    update_partner_resources_script(
        dist=dist,
        gh_pages=gh_pages,
        rdf_template_path=rdf_template_path,
        current_collection_format=current_collection_format,
    )
    fake_deploy(dist, gh_pages)

    updates = update_external_resources_script(collection=collection)
    print("would open auto-update PRs with:")
    pprint(updates)

    fake_deploy(dist, collection)

    end_of_step(always_continue)
    #################################
    # update rdfs (resource versions)
    #################################
    pending = update_rdfs_script(
        dist=dist, collection=collection, last_collection=last_collection, gh_pages=gh_pages, branch=None
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
        dist=artifacts / "static_validation_artifact",
        pending_matrix=json.dumps(
            dict(
                include=pending["pending_matrix"].get("include", [])
                + pending["pending_matrix_bioimageio"].get("include", [])
            )
        ),
    )
    print("\nstatic validation:")
    pprint(static_out)

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
            rdf_dirs=[gh_pages / "rdfs"],
            weight_format=matrix["weight_format"],
        )

    end_of_step(always_continue)
    #################
    # validate/deploy
    #################
    deploy_test_summaries_script(
        dist=dist,
        collection=collection,
        gh_pages=gh_pages,
        artifact_dir=artifacts,
        partner_test_summaries=partner_test_summaries,
    )

    fake_deploy(dist, gh_pages)

    end_of_step(always_continue)
    ##################
    # build-collection
    ##################
    generate_collection_rdf_script(collection=collection, dist=dist)

    fake_deploy(dist, gh_pages)


if __name__ == "__main__":
    typer.run(main)
