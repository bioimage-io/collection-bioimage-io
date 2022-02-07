from hashlib import sha256
from pathlib import Path
from typing import List, Optional, Tuple

import typer

from bare_utils import set_gh_actions_outputs
from bioimageio.core import __version__ as bioimageio_core_version
from bioimageio.spec import __version__ as bioimageio_spec_version
from bioimageio.spec.shared import yaml
from utils import write_rdfs_for_resource


def main(
    dist: Path = Path(__file__).parent / "../dist",
    collection: Path = Path(__file__).parent / "../collection",
    gh_pages: Path = Path(__file__).parent / "../gh-pages",
    branch: Optional[str] = None,
):
    """write updated rdfs to dist

    Args:
        dist: output folder
        collection: collection directory that holds resources as <resource_id>/resource.yaml
        gh_pages: directory with gh-pages checked out
        branch: (used in auto-update PR) If branch is 'auto-update-{resource_id} it is used to get resource_id
                and limit the update process to that resource.

    """
    if branch is not None and branch.startswith("auto-update-"):
        resource_id = branch[len("auto-update-") :]
    else:
        resource_id = "**"

    collection_resource_b = [r_path.open("rb").read() for r_path in collection.glob(f"{resource_id}/resource.yaml")]
    collection_resources = [(sha256(rb).hexdigest(), yaml.load(rb.decode("utf-8"))) for rb in collection_resource_b]
    partner_resources: List[Tuple[Optional[str], dict]] = [
        (None, yaml.load(r_path)) for r_path in (gh_pages / "partner_collection").glob(f"{resource_id}/resource.yaml")
    ]
    known_resources: List[Tuple[Optional[str], dict]] = [
        (h, r) for h, r in collection_resources + partner_resources if r["status"] == "accepted"
    ]

    include_pending = []
    include_pending_bioimageio_only = []
    for r_hash, r in known_resources:
        resource_id = r["id"]
        if r_hash is None:
            update_resource = False
        else:
            # check if resource and thus potentially updates to resource versions have changed
            r_hash_path = gh_pages / "rdfs" / resource_id / "resource_hash.txt"
            if r_hash_path.exists():
                last_r_hash = r_hash_path.read_text()
            else:
                last_r_hash = None

            update_resource = r_hash != last_r_hash
            if update_resource:
                r_hash_path = dist / r_hash_path.relative_to(gh_pages)
                r_hash_path.parent.mkdir(parents=True, exist_ok=True)
                r_hash_path.write_text(r_hash)

        update_only_bioimageio_validation = []
        for v in r["versions"]:
            if v["status"] != "accepted":
                continue

            version_id = v["version_id"]

            rdf_path = gh_pages / "rdfs" / resource_id / version_id / "rdf.yaml"
            test_summary_path = rdf_path.with_name("test_summary.yaml")

            if not update_resource and rdf_path.exists() and test_summary_path.exists():
                # check bioimageio versions
                test_summary = yaml.load(test_summary_path)
                if "bioimageio" not in test_summary:
                    test_summary["bioimageio"] = {}

                last_spec_version = test_summary["bioimageio"].get("bioimageio_spec_version")
                last_core_version = test_summary["bioimageio"].get("bioimageio_core_version")
                if last_spec_version != bioimageio_spec_version or last_core_version != bioimageio_core_version:
                    test_summary["bioimageio"]["bioimageio_spec_version"] = bioimageio_spec_version
                    test_summary["bioimageio"]["bioimageio_core_version"] = bioimageio_core_version
                    bioimageio_validation_pending = True
                else:
                    bioimageio_validation_pending = False
            else:
                update_resource = True
                bioimageio_validation_pending = True

            if bioimageio_validation_pending:
                update_only_bioimageio_validation.append(version_id)

        if update_resource:
            update_only_bioimageio_validation = []
            updated_versions = write_rdfs_for_resource(resource=r, dist=dist)
        else:
            updated_versions = []

        for v_id in updated_versions:
            include_pending.append({"resource_id": resource_id, "version_id": v_id})

        for v_id in update_only_bioimageio_validation:
            include_pending_bioimageio_only.append({"resource_id": resource_id, "version_id": v_id})

    out = dict(
        pending_matrix=dict(include=include_pending),
        has_pending_matrix=bool(include_pending),
        pending_matrix_only_bioimageio=dict(include=include_pending_bioimageio_only),
        has_pending_matrix_only_bioimageio=bool(include_pending_bioimageio_only),
    )
    set_gh_actions_outputs(out)
    return out


if __name__ == "__main__":
    typer.run(main)
