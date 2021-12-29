import json
from pathlib import Path

import requests
import typer
from ruamel.yaml import YAML

yaml = YAML(typ="safe")
MAIN_BRANCH_URL = (
    "https://raw.githubusercontent.com/bioimage-io/collection-bioimage-io/main"
)


def set_gh_actions_output(name: str, output: str):
    """set output of a github actions workflow step calling this script"""
    # escape special characters when setting github actions step output
    output = output.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::set-output name={name}::{output}")


def main(
    collection_folder: Path,
    branch: str = typer.Argument(
        ...,
        help="branch name should be 'auto-update-{resource_id} and is only used to get resource_id.",
    ),
) -> int:
    pending = []
    if branch.startswith("auto-update-"):
        resource_id = branch[len("auto-update-") :]
        resource_path = collection_folder / resource_id / "resource.yaml"
        response = requests.get(f"{MAIN_BRANCH_URL}/{resource_path}")
        if response.ok:
            previous_resource = yaml.load(response.text)
            previous_versions = {
                v["version_id"]: v for v in previous_resource["versions"]
            }
        else:
            previous_resource = None
            previous_versions = None
        resource = yaml.load(resource_path)
        # status of the entire resource item has changed
        if previous_resource and previous_resource.get("status") != resource.get(
            "status"
        ):
            pending = resource["versions"]
        else:
            for v in resource["versions"]:
                previous_version = previous_versions and previous_versions.get(
                    v["version_id"]
                )
                if previous_version is None or previous_version != v:  # check changes
                    pending.append(v["version_id"])
    else:
        # don't fail, but warn for non-auto-update branches
        print(f"called with non-auto-update branch {branch}")

    set_gh_actions_output("pending_matrix", json.dumps({"version_id": pending}))
    set_gh_actions_output("found_pending", "yes" if pending else "no")
    return 0


if __name__ == "__main__":
    typer.run(main)
