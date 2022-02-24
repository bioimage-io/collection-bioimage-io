"""script to run a rough equivalent of the github actions workflow 'collection_main.yaml' locally"""
import json
import shutil
import subprocess
from pathlib import Path
from pprint import pprint

import typer

from dynamic_validation import main as dynamic_validation_script
from generate_collection_rdf import main as generate_collection_rdf_script
from prepare_to_deploy import main as prepare_to_deploy_script
from static_validation import main as static_validation_script
from update_external_resources import main as update_external_resources_script
from update_partner_resources import main as update_partner_resources_script
from update_rdfs import main as update_rdfs_script
from utils import iterate_over_gh_matrix


def fake_deploy(dist: Path, deploy_to: Path):
    if dist.exists():
        shutil.copytree(str(dist), str(deploy_to), dirs_exist_ok=True)
        shutil.rmtree(str(dist))


def end_of_job(dist: Path, always_continue: bool):
    if not always_continue and input("Continue?([y]/n)").lower().startswith("n"):
        raise RuntimeError("abort")

    if dist.exists():
        shutil.rmtree(str(dist))


def main(always_continue: bool = True):
    # local setup
    collection = Path(__file__).parent / "../collection"

    rdf_template_path = Path(__file__).parent / "../collection_rdf_template.yaml"
    assert rdf_template_path.exists(), rdf_template_path

    partner_test_summaries = Path(__file__).parent / "../partner_test_summaries"
    if not partner_test_summaries.exists():
        partner_test_summaries.mkdir(parents=True)
        # todo: download partner_test_summaries

    gh_pages = Path(__file__).parent / "../gh-pages"
    if not gh_pages.exists():
        subprocess.run(["git", "worktree", "prune"], check=True)
        subprocess.run(["git", "worktree", "add", "--detach", str(gh_pages), "gh-pages"], check=True)

    last_collection = Path(__file__).parent / "../last_ci_run/collection"
    if not last_collection.parent.exists():
        subprocess.run(["git", "worktree", "prune"], check=True)
        subprocess.run(["git", "worktree", "add", "--detach", str(last_collection.parent), "last_ci_run"], check=True)

    dist = Path(__file__).parent / "../dist"
    if dist.exists():
        print(f"rm dist {dist}")
        shutil.rmtree(str(dist))

    artifacts = Path(__file__).parent / "../artifacts"
    if artifacts.exists():
        print(f"rm artifacts {artifacts}")
        shutil.rmtree(str(artifacts))

    ###################################
    # update resources (resource infos)
    ###################################
    updates = update_external_resources_script()
    print("would open auto-update PRs with:")
    pprint(updates)

    fake_deploy(dist, collection)  # in CI done via PRs

    update_partner_resources_script()
    fake_deploy(dist, gh_pages)

    end_of_job(dist, always_continue)
    #####################################################
    # update rdfs (resource versions) + static-validation
    #####################################################
    pending = update_rdfs_script()

    print("\npending (updated):")
    pprint(pending)

    # perform static validation for pending resources
    static_out = static_validation_script(
        pending_matrix=json.dumps(dict(include=pending["pending_matrix_bioimageio"].get("include", []))),
        dist=artifacts / "static_validation_artifact",
    )
    print("\nstatic validation:")
    pprint(static_out)

    end_of_job(dist, always_continue)
    #############################
    # validate/dynamic-validation
    #############################
    for matrix in iterate_over_gh_matrix(static_out["dynamic_test_cases"]):
        print(
            f"\ndynamic validation (r: {matrix['resource_id']}, v: {matrix['version_id']}, w: {matrix['weight_format']}):"
        )
        dynamic_validation_script(
            dist=artifacts / "dynamic_validation_artifact",
            resource_id=matrix["resource_id"],
            version_id=matrix["version_id"],
            weight_format=matrix["weight_format"],
        )

    end_of_job(dist, always_continue)
    #################
    # validate/deploy
    #################
    prepare_to_deploy_script()

    fake_deploy(dist / "gh_pages_update", gh_pages)

    end_of_job(dist, always_continue)
    ##################
    # build-collection
    ##################
    generate_collection_rdf_script()

    fake_deploy(dist, gh_pages)
    if pending["retrigger"]:
        print("incomplete collection update. needs additional run(s).")

    end_of_job(dist, always_continue)


if __name__ == "__main__":
    typer.run(main)
