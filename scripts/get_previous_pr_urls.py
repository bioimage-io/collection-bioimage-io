import argparse
import json
import warnings
from pathlib import Path

import requests

from bare_utils import RAW_BASE_URL, set_gh_actions_outputs


def main(resource_id: str, pr_urls_path: Path = Path(__file__).parent / "../dist/pr_urls.json"):
    try:
        r = requests.get(f"{RAW_BASE_URL}/pr_urls.json")
        r.raise_for_status()
        pr_urls = r.json()
    except Exception as e:
        warnings.warn(str(e))
        pr_urls = {}

    # save pr_urls for adding new pr url in a following step
    pr_urls_path.parent.mkdir(parents=True, exist_ok=True)
    with pr_urls_path.open("w", encoding="utf-8") as f:
        json.dump(pr_urls, f, ensure_ascii=False, indent=4)

    pr_urls_here = pr_urls.get(resource_id)
    if pr_urls_here:
        pr_urls_md = ", ".join(pr_urls_here)
    else:
        pr_urls_md = "none"

    set_gh_actions_outputs(dict(previous_prs=pr_urls_md))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Save PR url")
    parser.add_argument("resource_id", type=str)
    args = parser.parse_args()

    main(args.resource_id)
