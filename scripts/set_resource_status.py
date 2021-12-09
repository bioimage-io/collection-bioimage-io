import json
from pathlib import Path

import typer
from ruamel.yaml import YAML

yaml = YAML(typ="safe")


def main(
    collection_folder: Path,
    concept_doi: str,
    dois: str = typer.Argument(..., help="json string of list of dois"),
    status: str = typer.Argument(..., help="status to set"),
) -> int:
    dois = json.loads(dois)
    concept_path = collection_folder / concept_doi / "concept.yaml"
    concept = yaml.load(concept_path)
    for v in concept["versions"]:
        if v["doi"] in dois:
            v["status"] = status

    yaml.dump(concept, concept_path)
    return 0


if __name__ == "__main__":
    typer.run(main)
