import argparse
import json
from pathlib import Path


def main(resource_id: str, url: str, pr_urls_path: Path = Path(__file__).parent / "../dist/pr_urls.json"):
    if pr_urls_path.exists():
        with pr_urls_path.open() as f:
            pr_urls = json.load(f)
    else:
        pr_urls = {}

    pr_urls[resource_id] = pr_urls.get(resource_id, [])
    pr_urls[resource_id].append(url)

    with pr_urls_path.open("w", encoding="utf-8") as f:
        json.dump(pr_urls, f, ensure_ascii=False, indent=4)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Save PR url")
    parser.add_argument("resource_id", type=str)
    parser.add_argument("url", type=str)
    args = parser.parse_args()

    main(args.resource_id, args.url)
