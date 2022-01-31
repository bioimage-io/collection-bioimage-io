from pathlib import Path
from typing import Optional

import typer
from ruamel.yaml import YAML

from utils import set_gh_actions_outputs

yaml = YAML(typ="safe")


def main(
    collection_dir: Path = Path(__file__).parent / "../collection",
    gh_pages_dir: Path = Path(__file__).parent / "../gh-pages",
    branch: Optional[str] = typer.Option(
        None,
        help="(used in auto-update PR) If branch is 'auto-update-{resource_id} it is used to get resource_id and limit validation to unvalidated versions of that resource.",
    ),
):
    """output all accepted resource versions that are missing validation"""

    if branch is not None and branch.startswith("auto-update-"):
        resource_id = branch[len("auto-update-") :]
    else:
        resource_id = "**"

    collection_resources = [yaml.load(r_path) for r_path in collection_dir.glob(f"{resource_id}/resource.yaml")]
    partner_resources = [
        yaml.load(r_path) for r_path in (gh_pages_dir / "partner_collection").glob(f"{resource_id}/resource.yaml")
    ]
    known_resources = [r for r in collection_resources + partner_resources if r["status"] == "accepted"]

    include_pending = []
    for r in known_resources:
        resource_id = r["id"]
        for v in r["versions"]:
            if v["status"] != "accepted":
                continue

            version_id = v["version_id"]
            rdf_path = gh_pages_dir / "resources" / resource_id / version_id / "rdf.yaml"
            if rdf_path.exists():
                rdf = yaml.load(rdf_path)  # deployed RDF may already have test_summary
                is_pending = "test_summary" not in rdf.get("config", {}).get("bioimageio", {})
                # todo: check bioimageio version
            else:
                # not deployed (yet)
                is_pending = True
                rdf_path = None

            if is_pending:
                include_pending.append(
                    {
                        "resource_id": resource_id,
                        "version_id": version_id,
                        "rdf_path": rdf_path and str(rdf_path),
                        "rdf_source": v["rdf_source"],
                    }
                )

    out = dict(pending_matrix=dict(include=include_pending), has_pending_matrix=bool(include_pending))
    set_gh_actions_outputs(out)
    return out


if __name__ == "__main__":
    typer.run(main)
