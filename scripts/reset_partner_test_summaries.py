from pathlib import Path

from bioimageio.spec.shared import yaml
from utils import iterate_known_resource_versions


def main(
    partner_id: str,
    dist: Path = Path(__file__).parent / "../dist",
    collection: Path = Path(__file__).parent / "../collection",
    gh_pages: Path = Path(__file__).parent / "../gh-pages",
):
    """reset partner test summaries"""
    dist.mkdir(parents=True, exist_ok=True)
    for v in iterate_known_resource_versions(collection=collection, gh_pages=gh_pages, status="accepted"):
        test_summary_path = v.rdf_path.with_name("test_summary.yaml")
        if test_summary_path.exists():
            test_summary = yaml.load(test_summary_path)
            if "tests" in test_summary:
                test_summary["tests"] = {k: v for k, v in test_summary["tests"].items() if k != partner_id}
                test_summary_path = dist / test_summary_path.relative_to(gh_pages)
                yaml.dump(test_summary, test_summary_path)
