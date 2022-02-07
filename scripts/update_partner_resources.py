import warnings
from pathlib import Path

import typer

from utils import enforce_block_style_resource, resolve_partners, write_updated_resource_rdfs, yaml


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
    print("updated_partner_resources:")
    print(updated_partner_resources)

    if ignored_partners:
        warnings.warn(f"ignored invalid partners: {ignored_partners}")  # todo: raise instead of warning?

    deploy_partner_collections_path = dist / partner_collections_path.name
    deploy_partner_collections_path.parent.mkdir(exist_ok=True, parents=True)
    yaml.dump(updated_partner_collections, deploy_partner_collections_path)
    for r in updated_partner_resources:
        r_path = dist / "partner_collection" / r["id"] / "resource.yaml"
        r_path.parent.mkdir(exist_ok=True, parents=True)
        yaml.dump(enforce_block_style_resource(r), r_path)
        write_updated_resource_rdfs(dist, r)

    dist.mkdir(exist_ok=True, parents=True)
    yaml.dump(partners, dist / "partner_details.yaml")


if __name__ == "__main__":
    typer.run(main)
