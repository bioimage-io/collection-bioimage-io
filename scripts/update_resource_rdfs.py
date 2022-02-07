from pathlib import Path

import typer

from bioimageio.spec.shared import yaml
from utils import iterate_over_gh_matrix, write_updated_resource_rdfs


def main(
    dist: Path = Path(__file__).parent / "../dist",
    pending_matrix: str = "",
    collection_dir: Path = Path(__file__).parent / "../collection",
    gh_pages: Path = Path(__file__).parent / "../gh-pages",
):
    """write updated rdf to dist if missing for every case that is missing 'rdf_path'"""
    for matrix in iterate_over_gh_matrix(pending_matrix):

        resource_id = matrix["resource_id"]
        version_id = matrix["version_id"]
        resource_path = collection_dir / resource_id / "resource.yaml"
        if not resource_path.exists():
            resource_path = gh_pages / "partner_collection" / resource_id / "resource.yaml"

        assert resource_path.exists(), resource_path

        resource = yaml.load(resource_path)

        # limit resource to the single version at hand
        resource["versions"] = [v for v in resource.get("versions", []) if v["version_id"] == version_id]

        # write updated version rdf to dist
        write_updated_resource_rdfs(dist=dist, resource=resource)


if __name__ == "__main__":
    typer.run(main)
