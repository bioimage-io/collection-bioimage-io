import json
import shutil
import warnings
from datetime import datetime
from pathlib import Path
from pprint import pprint
from typing import Optional

import typer
from bioimageio.spec.shared import yaml
from boltons.iterutils import remap
from utils import deploy_thumbnails, iterate_known_resources, load_yaml_dict, rec_sort

SUMMARY_FIELDS = (
    "authors",
    "badges",
    "covers",
    "description",
    "download_url",
    "github_repo",
    "icon",
    "id",
    "license",
    "links",
    "name",
    "rdf_source",
    "source",
    "tags",
    "type",
    "versions",
    "training_data",
)

SUMMARY_FIELDS_FROM_CONFIG_BIOIMAGEIO = [
    "nickname",
    "nickname_icon",
    "owners",
]


def extend_links_from_test_summary(links: list, test_summary_path: Path) -> None:
    try:
        test_summary = load_yaml_dict(test_summary_path, raise_missing_keys=["tests"])
    except Exception as e:
        test_summary = None
        msg = f": {e}"
    else:
        msg = ""

    if test_summary is None:
        warnings.warn(f"Failed to extend links from test summary {test_summary_path}{msg}")
        return

    # todo: improve condition to link link software application
    # todo: maybe add link field to test_summary? maybe also link apps to failed tests?
    # todo: maybe a test (failed or not) can link resource(s)?
    for app in ["ilastik", "deepimage"]:
        app_link = f"{app}/{app}"
        if (
            app in test_summary["tests"]
            and all(t.get("status") == "passed" for t in test_summary["tests"][app])
            and app_link not in links
        ):
            links.append(app_link)


def main(
    collection: Path = Path(__file__).parent / "../collection",
    gh_pages: Path = Path(__file__).parent / "../gh-pages",
    rdf_template_path: Path = Path(__file__).parent
    / "../collection_rdf_template.yaml",  # todo: rename (not a valid rdf)
    dist: Path = Path(__file__).parent / "../dist",
):
    rdf = yaml.load(rdf_template_path)
    rdf["collection"] = rdf.get("collection", [])
    assert isinstance(rdf["collection"], list), type(rdf["collection"])

    download_counts_path = gh_pages / "download_counts.json"
    if download_counts_path.exists():
        with download_counts_path.open(encoding="utf-8") as f:
            download_counts = json.load(f) or {}
    else:
        download_counts = {}

    if "partners" in rdf["config"]:
        # load resolved partner details
        partner_details_path = gh_pages / "partner_details.json"
        if partner_details_path.exists():
            with partner_details_path.open() as f:
                rdf["config"]["partners"] = json.load(f)
        else:
            print(f"Missing evaluated partner details at {partner_details_path}")
    else:
        print('Missing "partners" in rdf["config"]!')

    n_accepted = {}
    n_accepted_versions = {}
    for r in iterate_known_resources(collection=collection, gh_pages=gh_pages):
        latest_version = None
        version_id: Optional[str] = None
        for version_info in r.info.get("versions", []):
            if version_info["status"] != "accepted":
                continue

            version_id = version_info["version_id"]
            rdf_path = gh_pages / "rdfs" / r.resource_id / version_id / "rdf.yaml"
            if not rdf_path.exists():
                print(f"skipping undeployed rdf: {r.resource_id}/{version_id}")
                continue

            this_version = yaml.load(rdf_path)
            if this_version is None:
                print(f"skipping empty rdf: {r.resource_id}/{version_id}")
                continue

            assert version_id == this_version["id"].split("/")[-1]
            assert r.resource_id == this_version["id"][: -(len(version_id) + 1)]

            if latest_version is None:
                latest_version = this_version
                latest_version["id"] = r.resource_id
                latest_version["versions"] = [version_id]
            else:
                latest_version["versions"].append(version_id)

        if latest_version is None:
            print(f"Ignoring resource {r.resource_id} without any accepted/deployed versions")
            continue

        assert version_id is not None
        summary = {k: latest_version[k] for k in latest_version if k in SUMMARY_FIELDS}
        for k in latest_version["config"]["bioimageio"]:
            if k in SUMMARY_FIELDS_FROM_CONFIG_BIOIMAGEIO:
                summary[k] = latest_version["config"]["bioimageio"][k]

        summary["download_count"] = download_counts.get(r.resource_id, 1)

        links = summary.get("links", [])
        extend_links_from_test_summary(links, gh_pages / "rdfs" / r.resource_id / version_id / "test_summary.yaml")
        if links:
            summary["links"] = links

        deploy_thumbnails(summary, dist, r.resource_id, version_id)
        rdf["collection"].append(summary)
        type_ = latest_version.get("type", "unknown")
        n_accepted[type_] = n_accepted.get(type_, 0) + 1
        n_accepted_versions[type_] = n_accepted_versions.get(type_, 0) + 1 + len(latest_version["versions"])

    print(f"new collection rdf contains {sum(n_accepted.values())} accepted resources.")
    print("accepted resources per type:")
    pprint(n_accepted)
    print("accepted resource versions per type:")
    pprint(n_accepted_versions)

    rdf["config"] = rdf.get("config", {})
    rdf["config"]["n_resources"] = n_accepted
    rdf["config"]["n_resource_versions"] = n_accepted_versions

    # check for unique nicknames
    nicknames = [e["nickname"] for e in rdf["collection"] if "nickname" in e]
    duplicate_nicknames = [nick for i, nick in enumerate(nicknames) if nick in nicknames[:i]]
    if duplicate_nicknames:
        raise ValueError(f"Duplicate nicknames: {duplicate_nicknames}")

    # sort collection
    rdf["collection"].sort(key=lambda c: -c["download_count"])

    # collection.json was previously saved as 'rdf.yaml'. # todo: remove 'rdf.yaml'
    collection_file_path = dist / "rdf.yaml"
    collection_file_path.parent.mkdir(exist_ok=True)
    yaml.dump(rec_sort(rdf), collection_file_path)

    def convert_for_json(p, k, v):
        """convert anything not json compatible"""
        # replace nans
        number_strings = ["-inf", "inf", "nan"]
        for n in number_strings:
            if v == float(n):
                return k, n

        if isinstance(v, datetime):
            return k, v.isoformat()

        return True

    collection_file_path = dist / "collection.json"
    rdf = remap(rdf, convert_for_json)
    collection_file_path.parent.mkdir(exist_ok=True)
    with open(collection_file_path, "w") as f:
        json.dump(rdf, f, allow_nan=False, indent=2, sort_keys=True)

    shutil.copy(
        str(collection_file_path), str(collection_file_path.with_name("rdf.json"))
    )  # deprecated; todo: 'rdf.json'


if __name__ == "__main__":
    typer.run(main)
