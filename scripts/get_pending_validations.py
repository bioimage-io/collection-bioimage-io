import warnings
from pathlib import Path

import typer
from ruamel.yaml import YAML

from utils import set_gh_actions_outputs

yaml = YAML(typ="safe")


def main(
    collection_dir: Path = Path(__file__).parent / "../collection",
    gh_pages_dir: Path = Path(__file__).parent / "../gh-pages",
):
    """output all accepted resource versions that are missing validation"""
    pending = []
    collection_resources = [yaml.load(r_path) for r_path in collection_dir.glob("**/resource.yaml")]
    partner_resources = [yaml.load(r_path) for r_path in (gh_pages_dir / "partner_collection").glob("**/resource.yaml")]
    known_resources = [r for r in collection_resources + partner_resources if r["status"] == "accepted"]
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
            else:
                # RDF not yet deployed?!
                warnings.warn(f"skip validating missing rdf: {rdf_path}")
                is_pending = False

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
