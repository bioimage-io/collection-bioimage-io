import json
import warnings
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

import typer

from bare_utils import set_gh_actions_outputs
from bioimageio.core import __version__ as core_version
from bioimageio.spec import __version__ as spec_version
from bioimageio.spec.shared import yaml
from utils import iterate_known_resources, write_rdfs_for_resource


def dict_eq_wo_keys(a: dict, b: dict, *ignore_keys):
    a_filtered = {k: v for k, v in a.items() if k not in ignore_keys}
    b_filtered = {k: v for k, v in b.items() if k not in ignore_keys}
    return a_filtered == b_filtered


PARTNERS_TEST_TYPES: Dict[str, List[str]] = dict(ilastik=["model"])


def main(
    dist: Path = Path(__file__).parent / "../dist/updated_rdfs",
    collection: Path = Path(__file__).parent / "../collection",
    last_collection: Path = Path(__file__).parent / "../last_ci_run/collection",
    gh_pages: Path = Path(__file__).parent / "../gh-pages",
    branch: str = "",
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
    branch = branch.replace("refs/heads/", "")
    if branch.startswith("auto-update-"):
        resource_id_pattern = branch[len("auto-update-") :]
    else:
        resource_id_pattern = "**"

    dist.mkdir(parents=True, exist_ok=True)

    retrigger = False
    pending_include = defaultdict(list)  # include section of gh style matrix for each partner and bioimageio
    for r in iterate_known_resources(
        collection=collection, gh_pages=gh_pages, resource_id=resource_id_pattern, status="accepted"
    ):
        if r.partner_resource:
            old_r_path = gh_pages / "partner_collection" / r.resource_id / "resource.yaml"
        else:
            # check if resource info has changed
            old_r_path = last_collection / r.resource_id / "resource.yaml"

        if old_r_path.exists():
            old_r_info = yaml.load(old_r_path)
            updated_resource_info = not dict_eq_wo_keys(r.info, old_r_info, "versions")
        else:
            updated_resource_info = True
            old_r_info = {"versions": []}

        limited_reeval = defaultdict(list)
        if updated_resource_info:
            updated_versions = write_rdfs_for_resource(resource=r.info, dist=dist)
        else:
            updated_versions = []
            # check for each version if an update occurred or if only specific partners need to reevaluate
            for v in r.info.get("versions", []):
                if v["status"] != "accepted":
                    continue

                version_id = v["version_id"]

                rdf_path = gh_pages / "rdfs" / r.resource_id / version_id / "rdf.yaml"
                test_summary_path = rdf_path.with_name("test_summary.yaml")

                if rdf_path.exists() and test_summary_path.exists():
                    # check if version info has changed
                    matching_old_versions = [
                        old_v for old_v in old_r_info.get("versions", []) if old_v["version_id"] == version_id
                    ]
                    version_has_update = not matching_old_versions or matching_old_versions[0] != v
                    if not version_has_update:
                        if test_summary_path.exists():
                            test_summary: Optional[dict] = yaml.load(test_summary_path)
                            if not (isinstance(test_summary, dict) and "tests" in test_summary):
                                warnings.warn(f"Ignoring invalid test summary {test_summary}")
                                test_summary = None
                        else:
                            test_summary = None

                        # check bioimageio library versions in test summary
                        if test_summary is not None:
                            last_spec_version = test_summary.get("bioimageio_spec_version")
                            last_core_version = test_summary.get("bioimageio_core_version")
                            if last_spec_version != spec_version or (
                                last_core_version is not None and last_core_version != core_version
                            ):
                                limited_reeval["bioimageio"].append(version_id)

                        # check if partner test is present if it should be
                        for partner_id, partner_val_types in PARTNERS_TEST_TYPES.items():
                            if (not test_summary or partner_id not in test_summary["tests"]) and r.info.get(
                                "type", "general"
                            ) in partner_val_types:
                                limited_reeval[partner_id].append(version_id)
                else:
                    version_has_update = True

                if version_has_update:
                    updated_versions += write_rdfs_for_resource(
                        resource=r.info, dist=dist, only_for_version_id=version_id
                    )

        # add to 'include' value of a gh style matrix
        for v_id in updated_versions:
            entry = {"resource_id": r.resource_id, "version_id": v_id}
            pending_include["bioimageio"].append(entry)
            for partner_id in PARTNERS_TEST_TYPES:
                pending_include[partner_id].append(entry)

        for partner_id, v_ids in limited_reeval.items():
            for v_id in v_ids:
                entry = {"resource_id": r.resource_id, "version_id": v_id}
                pending_include[partner_id].append(entry)

        if any(len(entries) > 100 for entries in pending_include.values()):
            retrigger = True
            break

    # create gh style matrices with 'include'
    pending_matrices = {
        "include": [
            dict(partner_id=partner_id, pending_matrix=json.dumps(dict(include=pending_include[partner_id])))
            for partner_id in PARTNERS_TEST_TYPES
        ]
    }
    out = dict(
        pending_matrices=pending_matrices,
        has_pending_matrices=bool(pending_matrices),
        pending_matrix_bioimageio=dict(include=pending_include["bioimageio"]),
        has_pending_matrix_bioimageio=bool(pending_include["bioimageio"]),
        retrigger=retrigger,
    )
    set_gh_actions_outputs(out)
    return out


if __name__ == "__main__":
    typer.run(main)
