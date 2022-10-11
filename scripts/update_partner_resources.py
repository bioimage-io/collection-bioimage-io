import json
import warnings
from pathlib import Path

import typer

from bioimageio.spec import __version__ as bioimageio_spec_version
from utils import enforce_block_style_resource, resolve_partners, write_rdfs_for_resource, yaml


def main(
    dist: Path = Path(__file__).parent / "../dist",
    gh_pages: Path = Path(__file__).parent / "../gh-pages",
    rdf_template_path: Path = Path(__file__).parent / "../collection_rdf_template.yaml",
    current_collection_format: str = "0.2.2",
):
    dist.mkdir(parents=True, exist_ok=True)
    rdf = yaml.load(rdf_template_path)

    partner_hashes_path = gh_pages / "partner_collection_hashes.json"
    partner_hashes = json.loads(partner_hashes_path.read_text(encoding="utf-8")) if partner_hashes_path.exists() else {}
    # reset partner hashes if bioimageio.spec version has changed
    if partner_hashes.get("bioimageio_spec_version") != bioimageio_spec_version:
        partner_hashes = {"bioimageio_spec_version": bioimageio_spec_version}

    partners, updated_partner_resources, new_partner_hashes, ignored_partners = resolve_partners(
        rdf, current_format=current_collection_format, previous_partner_hashes=partner_hashes
    )

    if ignored_partners:
        warnings.warn(f"ignored invalid partners: {ignored_partners}")  # todo: raise instead of warning?

    # find deleted partner resources
    updated_partner_ids = {r["id"] for r in updated_partner_resources}
    for p in new_partner_hashes:  # only check updated partners
        for r_path in (gh_pages / "partner_collection" / p).glob("*/resource.yaml"):
            r_id = f"{p}/{r_path.name}"
            if r_id not in updated_partner_ids:
                updated_partner_resources.append(dict(status="deleted", id=r_id))

    # update resource.yaml for updated partner resources
    for r in updated_partner_resources:
        r_path = dist / "partner_collection" / r["id"] / "resource.yaml"
        r_path.parent.mkdir(exist_ok=True, parents=True)
        yaml.dump(enforce_block_style_resource(r), r_path)
        write_rdfs_for_resource(resource=r, dist=dist)

    dist.mkdir(exist_ok=True, parents=True)
    with (dist / "partner_details.json").open("w", encoding="utf-8") as f:
        json.dump(partners, f, ensure_ascii=False, indent=4, sort_keys=True)

    partner_hashes.update(new_partner_hashes)
    partner_hashes_path = dist / partner_hashes_path.relative_to(gh_pages)
    partner_hashes_path.parent.mkdir(exist_ok=True, parents=True)
    partner_hashes_path.write_text(json.dumps(partner_hashes, indent=2, sort_keys=True), encoding="utf-8")
    print(f"{len(new_partner_hashes)}/{len(partners)} partners updated")


if __name__ == "__main__":
    typer.run(main)
