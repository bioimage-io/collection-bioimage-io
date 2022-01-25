from pathlib import Path

import typer
from ruamel.yaml import YAML

from utils import resolve_partners, set_gh_actions_outputs

yaml = YAML(typ="safe")
MAIN_BRANCH_URL = "https://raw.githubusercontent.com/bioimage-io/collection-bioimage-io/main"


def main(
    collection_dir: Path = Path(__file__).parent / "../collection",
    gh_pages_dir: Path = Path(__file__).parent / "../gh-pages",
    collection_rdf_template_path: Path = Path(__file__).parent / "../collection_rdf_template.yaml",
):
    """output all accepted resource versions that are missing (static) validation"""
    resources_dir = gh_pages_dir / "resources"

    pending = []
    collection_resources = [yaml.load(r_path) for r_path in collection_dir.glob("**/resource.yaml")]
    collection_resources = [r for r in collection_resources if r["status"] == "accepted"]
    partners, partner_resources, updated_partners, ignored_partners = resolve_partners(
        yaml.load(collection_rdf_template_path)
    )
    known_resources = partner_resources + collection_resources
    for r in known_resources:
        resource_id = r["id"]
        for v in r["versions"]:
            if v["status"] != "accepted":
                continue

            version_id = v["version_id"]
            rdf_path = resources_dir / resource_id / version_id / "rdf.yaml"
            if rdf_path.exists():
                rdf = yaml.load(rdf_path)  # deployed RDF may already have test_summary
                is_pending = "test_summary" not in rdf.get("config", {}).get("bioimageio", {})
            else:
                is_pending = False  # RDF not yet deployed

            if is_pending:
                pending.append((resource_id, version_id))

    out = dict(
        pending_matrix=dict(include=[{"resource_id": rid, "version_id": vid} for rid, vid in pending]),
        has_pending_matrix=bool(pending),
    )
    set_gh_actions_outputs(out)
    return out


if __name__ == "__main__":
    typer.run(main)
