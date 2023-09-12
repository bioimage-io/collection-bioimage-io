"""script to run a rough equivalent of the github actions workflow 'collection_main.yaml' locally"""
import io
import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from pprint import pprint

import requests
import typer
from bare_utils import GH_API_URL, GITHUB_REPOSITORY_OWNER
from dynamic_validation import main as dynamic_validation_script
from prepare_to_deploy import main as prepare_to_deploy_script
from static_validation import main as static_validation_script
from update_external_resources import main as update_external_resources_script
from update_partner_resources import main as update_partner_resources_script
from update_rdfs import main as update_rdfs_script
from utils import iterate_over_gh_matrix

from scripts.generate_collection_rdf_and_thumbnails import main as generate_collection_rdf_and_thumbnails_script


def download_from_gh(owner: str, repo: str, branch: str, folder: Path):
    r = requests.get(
        f"{ GH_API_URL }/repos/{ owner }/{ repo }/commits/{ branch }",
        headers=dict(Accept="application/vnd.github.v3+json"),
    )
    r.raise_for_status()
    sha = r.json()["sha"]
    r = requests.get(f"https://github.com/{owner}/{repo}/archive/{sha}.zip")
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    with tempfile.TemporaryDirectory() as temp:
        z.extractall(temp)
        shutil.move(temp + f"/{repo}-{sha}", folder)


def fake_deploy(dist: Path, deploy_to: Path):
    if dist.exists():
        shutil.copytree(str(dist), str(deploy_to), dirs_exist_ok=True)


def end_of_job(dist: Path, always_continue: bool):
    if not always_continue and input("Continue?([y]/n)").lower().startswith("n"):
        raise RuntimeError("abort")

    if dist.exists():
        shutil.rmtree(str(dist))


def main(always_continue: bool = True, skip_update_external: bool = True, with_state: bool = True):
    """run a close equivalent to the 'update collection' (auto_update_main.yaml) workflow.
    # todo: improve this script and substitute the GitHub Actions CI with it in order to make deployment more transparent

    Args:
        always_continue: Set to False for debugging to pause between individual deployment steps
        skip_update_external: Don't query zenodo.org for new relevant records
        with_state: checkout current 'gh-pages' branch and 'lst_ci_run" tag to evaluate difference only

    """
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
        if with_state:
            download_from_gh(GITHUB_REPOSITORY_OWNER, "collection-bioimage-io", "gh-pages", gh_pages)
        else:
            gh_pages.mkdir()

    last_collection = Path(__file__).parent / "../last_ci_run/collection"
    if not last_collection.parent.exists():
        if with_state:
            download_from_gh(GITHUB_REPOSITORY_OWNER, "collection-bioimage-io", "last_ci_run", last_collection.parent)
        else:
            last_collection.mkdir(parents=True)

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
    if not skip_update_external:
        updates = update_external_resources_script()
        print("would open auto-update PRs with:")
        pprint(updates)

        # super fake deploy
        shutil.move((dist / "download_counts.json").as_posix(), "tmp_download_counts.json")

        fake_deploy(dist, collection)  # in CI done via PRs

    if dist.exists():
        shutil.rmtree(str(dist))
        tmp_dwn_counts = Path("tmp_download_counts.json")
        if tmp_dwn_counts.exists():
            dist.mkdir(parents=True)
            shutil.move(tmp_dwn_counts.as_posix(), (dist / "download_counts.json").as_posix())

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
    prepare_to_deploy_script(local=True)

    fake_deploy(dist / "gh_pages_update", gh_pages)

    end_of_job(dist, always_continue)
    ##################
    # build-collection
    ##################
    generate_collection_rdf_and_thumbnails_script()

    fake_deploy(dist, gh_pages)
    if pending["retrigger"]:
        print("incomplete collection update. needs additional run(s).")

    end_of_job(dist, always_continue)

    # copy _header and index.html file in order to enable a valid bioimage.io preview
    shutil.copy(Path(__file__).parent / "../_headers", str(gh_pages / "_headers"))
    shutil.copy(Path(__file__).parent / "../index.html", str(gh_pages / "index.html"))


if __name__ == "__main__":
    typer.run(main)
