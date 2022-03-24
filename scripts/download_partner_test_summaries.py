import subprocess
import warnings
from pathlib import Path

import typer

from bioimageio.spec.shared import yaml


def main(
    collection_template_path: Path = Path(__file__).parent / "../collection_rdf_template.yaml",
    partner_test_summaries: Path = Path(__file__).parent
    / "../partner_test_summaries",  # folder to save partner test summaries to
):
    for p in yaml.load(collection_template_path).get("config", {}).get("partners", []):
        if "test_summaries" not in p:
            continue
        ts = p["test_summaries"]
        cmd = [
            "svn",
            "export",
            f"https://github.com/{ts['repository']}/branches/{ts['deploy_branch']}/{ts['deploy_folder']}",
            str(partner_test_summaries / p["id"]),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 or r.stderr:
            warnings.warn(f"{' '.join(cmd)}\n{r.stdout}\n{r.stderr}")


if __name__ == "__main__":
    typer.run(main)
