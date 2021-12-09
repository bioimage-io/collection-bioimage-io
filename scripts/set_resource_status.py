import json
from pathlib import Path

import typer
from ruamel.yaml import YAML

yaml = YAML(typ="safe")


def main(
    collection_folder: Path,
    concept_doi: str,
    version_ids: str = typer.Argument(..., help="json string of list of dois"),
    status: str = typer.Argument(..., help="status to set"),
) -> int:
    version_ids = json.loads(version_ids)
    concept_path = collection_folder / concept_doi / "concept.yaml"
    concept = yaml.load(concept_path)
    for v in concept["versions"]:
        if v["version_id"] in version_ids:
            v["status"] = status

    yaml.dump(concept, concept_path)
    return 0


if __name__ == "__main__":
    typer.run(main)
