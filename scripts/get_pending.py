import json
import warnings
from pathlib import Path

import typer
from ruamel.yaml import YAML

from script_utils import set_gh_actions_output

yaml = YAML(typ="safe")


def main(
    collection_folder: Path,
    branch: str = typer.Argument(
        ..., help="branch name should be 'auto-update-{resource_id} and is only used to get resource_id."
    ),
) -> int:
    pending = []
    if branch.startswith("auto-update-"):
        resource_id = branch[len("auto-update-") :]

        resource_path = collection_folder / resource_id / "resource.yaml"
        resource = yaml.load(resource_path)
        for v in resource["versions"]:
            if v["status"] == "pending":
                pending.append(v["version_id"])

    else:
        # don't fail, but warn for non-auto-update branches
        warnings.warn(f"called with non-auto-update branch {branch}")

    set_gh_actions_output("pending_matrix", json.dumps({"version_id": pending}))
    # set_gh_actions_output("found_pending", "yes" if pending else "no")
    return 0


if __name__ == "__main__":
    typer.run(main)
