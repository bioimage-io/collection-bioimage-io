import warnings
from distutils.version import StrictVersion
from pathlib import Path

import typer
from ruamel.yaml import YAML

from utils import resolve_partners, update_resource_rdfs

yaml = YAML(typ="safe")


def main(
    dist: Path = Path(__file__).parent / "../dist",
    gh_pages: Path = Path(__file__).parent / "../gh-pages",
    rdf_template_path: Path = Path(__file__).parent / "../collection_rdf_template.yaml",
    current_collection_format: str = "0.2.2",
):
    partner_versions_path = gh_pages / "partner_versions.yaml"
    if partner_versions_path.exists():
        partner_versions = {k: StrictVersion(v) for k, v in yaml.load(partner_versions_path).items()}
    else:
        partner_versions = {}

    rdf = yaml.load(rdf_template_path)

    partners, updated_partner_resources, updated_partner_versions, ignored_partners = resolve_partners(
        rdf, current_format=current_collection_format, partner_versions=partner_versions
    )
    if "partners" in rdf["config"]:
        rdf["config"]["partners"] = partners
        print(f"{len(updated_partner_versions)}/{len(partners)} partners updated")

    if ignored_partners:
        warnings.warn(f"ignored invalid partners: {ignored_partners}")  # todo: raise instead of warning?

    for r in updated_partner_resources:
        yaml.dump(r, dist / "partner_collection" / r["id"] / "resource.yaml")
        update_resource_rdfs(dist, r)

    yaml.dump({k: str(v) for k, v in updated_partner_versions.items()}, partner_versions_path)
    yaml.dump(partners, dist / "partner_details.yaml")


if __name__ == "__main__":
    typer.run(main)
