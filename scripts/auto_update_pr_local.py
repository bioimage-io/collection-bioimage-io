"""script to run a rough equivalent of the github actions workflow 'auto_update_pr.yaml' locally"""
from pathlib import Path

import typer

from get_pending import main as get_pending


def main(resource_id: str, collection_folder: Path = Path(__file__).parent / "../collection"):
    pending = get_pending(collection_folder, f"auto-update-{resource_id}")
    print(pending)


if __name__ == "__main__":
    typer.run(main)
