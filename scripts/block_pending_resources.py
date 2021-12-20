import warnings
from pathlib import Path

import typer
from ruamel.yaml import YAML

yaml = YAML(typ="safe")


def set_gh_actions_output(name: str, output: str):
    """set output of a github actions workflow step calling this script"""
    # escape special characters when setting github actions step output
    output = output.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::set-output name={name}::{output}")


def main(
    collection_folder: Path,
    branch: str = typer.Argument(..., help="branch name should be 'auto-update-{id} and is only used to get id."),
) -> int:
    made_changes = False
    if branch.startswith("auto-update-"):
        id_ = branch[len("auto-update-") :]

        resource_path = collection_folder / id_ / "resource.yaml"
        resource = yaml.load(resource_path)
        for v in resource["versions"]:
            if v["status"] == "pending":
                v["status"] = "blocked"
                made_changes = True

        if any(v["status"] == "accepted" for v in resource["versions"]):
            resource_status = "accepted"
        else:
            resource_status = "blocked"

        if resource["status"] != resource_status:
            resource["status"] = resource_status
            made_changes = True

        if made_changes:
            yaml.dump(resource, resource_path)

    else:
        # don't fail, but warn for non-auto-update branches
        warnings.warn(f"called with non-auto-update branch {branch}")

    set_gh_actions_output("made_changes", "yes" if made_changes else "no")
    return 0


if __name__ == "__main__":
    typer.run(main)
