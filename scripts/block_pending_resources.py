from pathlib import Path

import typer
from ruamel.yaml import YAML

from utils import set_gh_actions_output

yaml = YAML(typ="safe")


def main(
    collection_dir: Path,
    branch: str = typer.Argument(..., help="branch name should be 'auto-update-{id} and is only used to get id."),
) -> int:
    made_changes = False
    if branch.startswith("auto-update-"):
        id_ = branch[len("auto-update-") :]

        resource_path = collection_dir / id_ / "resource.yaml"
        resource = yaml.load(resource_path)
        for v in resource["versions"]:
            if v["status"] == "pending":
                v["status"] = "blocked"
                made_changes = True

        if made_changes:
            yaml.dump(resource, resource_path)

    else:
        # don't fail, but warn for non-auto-update branches
        print(f"called with non-auto-update branch {branch}")

    set_gh_actions_output("made_changes", "yes" if made_changes else "no")
    return 0


if __name__ == "__main__":
    typer.run(main)
