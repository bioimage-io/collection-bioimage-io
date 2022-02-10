from pathlib import Path
from typing import Optional

import typer

from bare_utils import set_gh_actions_outputs
from bioimageio.core import __version__ as core_version
from bioimageio.spec import __version__ as spec_version
from bioimageio.spec.shared import yaml
from utils import iterate_known_resources, write_rdfs_for_resource


def main(
    dist: Path = Path(__file__).parent / "../dist",
    collection: Path = Path(__file__).parent / "../collection",
    last_collection: Path = Path(__file__).parent / "../last_ci_run/collection",
    gh_pages: Path = Path(__file__).parent / "../gh-pages",
    branch: Optional[str] = None,
):
    """write updated rdfs to dist

    Args:
        dist: output folder
        collection: collection directory that holds resources as <resource_id>/resource.yaml
        last_collection: collection directory at commit of last successful main ci run
        gh_pages: directory with gh-pages checked out
        branch: (used in auto-update PR) If branch is 'auto-update-{resource_id} it is used to get resource_id
                and limit the update process to that resource.

    """
    if branch is not None and branch.startswith("auto-update-"):
        resource_id_pattern = branch[len("auto-update-") :]
    else:
        resource_id_pattern = "**"

    retrigger = False
    include_pending = []
    include_pending_bioimageio = []
    for r in iterate_known_resources(
        collection=collection, gh_pages=gh_pages, resource_id=resource_id_pattern, status="accepted"
    ):
        if r.info_sha256 is None:
            update_resource = False
        else:
            # check if resource and thus potentially updates to resource versions have changed
            r_hash_path = gh_pages / "rdfs" / r.resource_id / "resource_hash.txt"
            if r_hash_path.exists():
                last_r_hash = r_hash_path.read_text()
            else:
                last_r_hash = None

            update_resource = r.info_sha256 != last_r_hash
            if update_resource:
                r_hash_path = dist / r_hash_path.relative_to(gh_pages)
                r_hash_path.parent.mkdir(parents=True, exist_ok=True)
                r_hash_path.write_text(r.info_sha256)

        update_bioimageio_validation = []
        for v in r.info["versions"]:
            if v["status"] != "accepted":
                continue

            version_id = v["version_id"]

            rdf_path = gh_pages / "rdfs" / r.resource_id / version_id / "rdf.yaml"
            test_summary_path = rdf_path.with_name("test_summary.yaml")

            if not update_resource and rdf_path.exists() and test_summary_path.exists():
                # check bioimageio versions
                test_summary = yaml.load(test_summary_path)
                if "bioimageio" not in test_summary:
                    bioimageio_validation_pending = True
                else:
                    last_spec_version = test_summary["bioimageio"].get("spec_version")
                    last_core_version = test_summary["bioimageio"].get("core_version")
                    bioimageio_validation_pending = (
                        last_spec_version != spec_version or last_core_version != core_version
                    )
            else:
                update_resource = True
                bioimageio_validation_pending = True

            if bioimageio_validation_pending:
                update_bioimageio_validation.append(version_id)

        if update_resource:
            update_bioimageio_validation = []
            updated_versions = write_rdfs_for_resource(resource=r.info, dist=dist)
        else:
            updated_versions = []

        for v_id in updated_versions:
            entry = {"resource_id": r.resource_id, "version_id": v_id}
            include_pending.append(entry)
            include_pending_bioimageio.append(entry)

        for v_id in update_bioimageio_validation:
            entry = {"resource_id": r.resource_id, "version_id": v_id}
            include_pending_bioimageio.append(entry)

        if len(include_pending_bioimageio) > 100:
            retrigger = True
            break

    out = dict(
        pending_matrix=dict(include=include_pending),
        has_pending_matrix=bool(include_pending),
        pending_matrix_bioimageio=dict(include=include_pending_bioimageio),
        has_pending_matrix_bioimageio=bool(include_pending_bioimageio),
        retrigger=retrigger,
    )
    set_gh_actions_outputs(out)
    return out


if __name__ == "__main__":
    typer.run(main)
