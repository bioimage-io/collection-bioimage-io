import warnings
from functools import partial
from pathlib import Path

import typer
from bioimageio.spec.shared import resolve_source
from tqdm import tqdm
from utils import yaml


def main(
    folder: Path = Path(__file__).parent
    / "../dist",  # nested folders with rdf.yaml files
):
    """Download the documentation file for every rdf.yaml found in (subfolders of) folder"""
    if not folder.exists():
        warnings.warn(f"{folder} not found")
        return

    for rdf_path in folder.glob("**/rdf.yaml"):
        rdf = yaml.load(rdf_path)
        if not isinstance(rdf, dict):
            warnings.warn(f"rdf not a dict: {rdf_path}")
            continue

        doc_uri = rdf.get("documentation")
        if not isinstance(doc_uri, str):
            warnings.warn(f"rdf['documentation'] not a string: {rdf_path}")
            continue

        if "." in str(doc_uri):
            type_ext = str(doc_uri).split(".")[-1]
        else:
            type_ext = "md"

        try:
            resolve_source(
                doc_uri,
                output=rdf_path.with_name(f"documentation.{type_ext}"),
                pbar=partial(tqdm, disable=True),
            )
        except Exception as e:
            warnings.warn(f"failed to resolve doc_ui: {e}")
            _ = rdf_path.with_name("documentation.md").write_text(doc_uri)


if __name__ == "__main__":
    typer.run(main)
