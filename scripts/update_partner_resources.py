import warnings
from pathlib import Path

import typer

from bioimageio.spec.shared import yaml
from utils import resolve_partners, update_resource_rdfs


def main(
    dist: Path = Path(__file__).parent / "../dist",
    gh_pages: Path = Path(__file__).parent / "../gh-pages",
    rdf_template_path: Path = Path(__file__).parent / "../collection_rdf_template.yaml",
    current_collection_format: str = "0.2.2",
):
    rdf = yaml.load(rdf_template_path)

    partner_collections_path = gh_pages / "partner_collection_snapshots.yaml"
    previous_partner_collections = yaml.load(partner_collections_path) if partner_collections_path.exists() else {}

    partners, updated_partner_resources, updated_partner_collections, ignored_partners = resolve_partners(
        rdf, current_format=current_collection_format, previous_partner_collections=previous_partner_collections
    )
    print(f"{len(updated_partner_collections)}/{len(partners)} partners updated")

    if ignored_partners:
        warnings.warn(f"ignored invalid partners: {ignored_partners}")  # todo: raise instead of warning?

    yaml.dump(updated_partner_collections, partner_collections_path)
    for r in updated_partner_resources:
        yaml.dump(r, dist / "partner_collection" / r["id"] / "resource.yaml")
        update_resource_rdfs(dist, r)

    yaml.dump(partners, dist / "partner_details.yaml")


if __name__ == "__main__":
    typer.run(main)
