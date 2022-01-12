from pathlib import Path

import typer
from ruamel.yaml import YAML

from utils import set_gh_actions_outputs

yaml = YAML(typ="safe")
MAIN_BRANCH_URL = "https://raw.githubusercontent.com/bioimage-io/collection-bioimage-io/main"


def main(
    collection_dir: Path = Path(__file__).parent / "../collection",
    gh_pages_dir: Path = Path(__file__).parent / "../gh-pages",
):
    """output all accepted resource versions that are missing (static) validation"""
    resources_dir = gh_pages_dir / "resources"

    pending = []
    for r_path in collection_dir.glob("**/resource.yaml"):
        r = yaml.load(r_path)
        if r["status"] != "accepted":
            continue

        resource_id = r["id"]
        for v in r["versions"]:
            if v["status"] != "accepted":
                continue

            version_id = v["version_id"]
            val_path = resources_dir / resource_id / version_id / "validation_summary_static.yaml"
            if not val_path.exists():
                pending.append((resource_id, version_id))

    out = dict(
        pending_matrix=dict(include=[{"resource_id": rid, "version_id": vid} for rid, vid in pending]),
        has_pending_matrix=bool(pending),
    )
    set_gh_actions_outputs(out)
    return out


if __name__ == "__main__":
    typer.run(main)
