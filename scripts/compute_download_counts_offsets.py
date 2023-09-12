import json
from pathlib import Path

import requests

gh_pages = Path(__file__).parent / "../gh-pages"

download_offsets = {}
for page in range(1, 1000):
    zenodo_request = (
        f"https://zenodo.org/api/records/?&sort=mostrecent&page={page}&size=1000&all_versions=1&keywords=bioimage.io"
    )
    r = requests.get(zenodo_request)
    if not r.status_code == 200:
        print(f"Could not get zenodo records page {page}: {r.status_code}: {r.reason}")
        break

    print(f"Collecting items from zenodo: {zenodo_request}")

    hits = r.json()["hits"]["hits"]
    if not hits:
        break

    for hit in hits:
        resource_doi = hit["conceptdoi"]
        doi = hit["doi"]  # "version" doi

        total_size = sum(f["size"] for f in hit["files"])
        download_count = int(hit["stats"]["unique_downloads"])
        downloaded_volume = int(hit["stats"]["version_volume"])
        desired_count = round(downloaded_volume / total_size)

        download_offsets[resource_doi] = desired_count - download_count


print(download_offsets)
with (Path(__file__).parent / "download_counts_offsets.json").open("w") as f:
    json.dump(download_offsets, f)
