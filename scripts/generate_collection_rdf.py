import json
import shutil
import subprocess
import warnings
from pathlib import Path
from pprint import pprint

import typer
from ruamel.yaml import YAML

yaml = YAML(typ="safe")


def set_gh_actions_output(name: str, output: str):
    """set output of a github actions workflow step calling this script"""
    # escape special characters when setting github actions step output
    output = output.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::set-output name={name}::{output}")


def main() -> int:
    collection_path = Path("collection")
    rdf = yaml.load(Path("collection_rdf_template.yaml"))

    subprocess.run(["git", "fetch"])
    remote_branch_proc = subprocess.run(["git", "branch", "-r"], capture_output=True, text=True)
    remote_branches = remote_branch_proc.stdout.split()
    print("found remote branches:")
    pprint(remote_branches)

    gh_pages = Path("dist/gh-pages")
    subprocess.run(["git", "worktree", "add", str(gh_pages), f"gh-pages"])
    gh_pages_previews = Path("dist/gh-pages-previews")
    gh_pages_update = Path("dist/gh-pages-update")
    gh_pages_update.mkdir(parents=True)

    processed_gh_pages_previews = []

    for r_path in collection_path.glob("**/resource.yaml"):
        r = yaml.load(r_path)
        if r["status"] != "accepted":
            continue

        latest_version = None
        for v in r["versions"]:
            if v["status"] != "accepted":
                continue

            # deploy from preview if it exists
            preview_branch = f"gh-pages-auto-update-{r['version_id']}"
            if f"origin/{preview_branch}" in remote_branches:
                # checkout preview separately
                ghp_preview = gh_pages_previews / preview_branch
                subprocess.run(["git", "worktree", "add", str(ghp_preview), f"{preview_branch}"])
                v_path = ghp_preview / "resources" / v["version_id"] / "rdf.yaml"
                # move gh-pages preview content to gh-pages update
                if v_path.exists():
                    processed_gh_pages_previews.append(preview_branch)
                    shutil.move(str(ghp_preview / "*"), str(gh_pages_update))
                    v_path = gh_pages_update / "resources" / v["version_id"] / "rdf.yaml"
            else:
                v_path = gh_pages / "resources" / v["version_id"] / "rdf.yaml"

            if not v_path.exists():
                warnings.warn(f"ignoring missing resource version {v_path}")
                continue

            this_version = yaml.load(v_path)
            if not isinstance(this_version, dict):
                warnings.warn(f"ignoring non-dict resource version {v_path}")
                continue

            # add validation summaries
            val_summaries = {}
            for val_path in v_path.parent.glob("validation_summary_*.yaml"):
                name = val_path.stem.replace("validation_summary_", "")
                val_sum = yaml.load(val_path)
                if not isinstance(val_sum, dict):
                    val_sum = {"output": val_sum}

                val_summaries[name] = {k: v for k, v in val_sum.items() if k != "source_name"}

            this_version["validation_summaries"] = val_summaries

            if latest_version is None:
                latest_version = this_version
                latest_version["previous_versions"] = []
            else:
                latest_version["previous_versions"].append(this_version)

        if latest_version is None:
            warnings.warn(f"Ignoring resource at {r_path} without any accepted versions")
        else:
            type_ = latest_version.get("type", "unknown")
            type_list = rdf.get(type_)
            if isinstance(type_list, list):
                type_list.append(latest_version)
            else:
                warnings.warn(f"ignoring resource {r_path} with type '{type_}'")

    rdf_path = Path("dist/gh-pages-update/rdf.yaml")
    rdf_path.parent.mkdir(exist_ok=True)
    yaml.dump(rdf, rdf_path)
    with open(rdf_path.with_suffix(".json"), "w") as f:
        json.dump(rdf, f)

    set_gh_actions_output("processed_gh_pages_previews", json.dumps({"preview-branch": processed_gh_pages_previews}))
    set_gh_actions_output("processed_any_gh_pages_previews", "yes" if processed_gh_pages_previews else "no")
    return 0


if __name__ == "__main__":
    typer.run(main)
