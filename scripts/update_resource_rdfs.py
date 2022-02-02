from pathlib import Path

import typer

from bioimageio.spec.shared import yaml
from utils import iterate_over_gh_matrix, set_gh_actions_outputs, update_resource_rdfs


def main(
    dist: Path = Path(__file__).parent / "../dist",
    pending_matrix: str = "",
    collection_dir: Path = Path(__file__).parent / "../collection",
    gh_pages: Path = Path(__file__).parent / "../gh-pages",
    future_deployed_path: Path = Path(__file__).parent
    / "../gh-pages",  # we write rdfs to dist, they won't be there in the next github actions job though...
) -> dict:
    """write updated rdf for every case that is missing 'rdf_path'"""
    updated_pending_include = []
    for matrix in iterate_over_gh_matrix(pending_matrix):
        if matrix["rdf_path"] is not None:
            updated_pending_include.append(matrix)
            continue

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
        updated_version_rdfs = update_resource_rdfs(dist=dist, resource=resource)

        matrix["rdf_path"] = str(future_deployed_path / updated_version_rdfs[version_id].relative_to(dist))

        updated_pending_include.append(matrix)

    out = dict(pending_matrix=dict(include=updated_pending_include), has_pending_matrix=bool(updated_pending_include))
    set_gh_actions_outputs(out)
    return out


if __name__ == "__main__":
    typer.run(main)
