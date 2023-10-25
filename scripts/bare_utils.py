"""standard lib only utils"""
import hashlib
import json
import os
import uuid
import warnings
from pathlib import Path
from typing import Any, Dict, Union

GITHUB_REPOSITORY_OWNER = os.getenv("GITHUB_REPOSITORY_OWNER", "bioimage-io")
DEPLOYED_BASE_URL = f"https://{GITHUB_REPOSITORY_OWNER}.github.io/collection-bioimage-io"
RAW_BASE_URL = f"https://raw.githubusercontent.com/{os.getenv('GITHUB_REPOSITORY_OWNER', 'bioimage-io')}/collection-bioimage-io/main"
GH_API_URL = "https://api.github.com"


def set_gh_actions_outputs(outputs: Dict[str, Union[str, Any]]):
    for name, out in outputs.items():
        set_gh_actions_output(name, out)


def set_gh_actions_output(name: str, output: Union[str, Any]):
    """set output of a github actions workflow step calling this script"""
    if isinstance(output, bool):
        output = "yes" if output else "no"

    if not isinstance(output, str):
        output = json.dumps(output, sort_keys=True)

    if "GITHUB_OUTPUT" not in os.environ:
        print(output)
        return

    if "\n" in output:
        with open(os.environ["GITHUB_OUTPUT"], "a") as fh:
            delimiter = uuid.uuid1()
            print(f"{name}<<{delimiter}", file=fh)
            print(output, file=fh)
            print(delimiter, file=fh)
    else:
        with open(os.environ["GITHUB_OUTPUT"], "a") as fh:
            print(f"{name}={output}", file=fh)


def get_sha256(path: Path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(h.block_size)
            if not block:
                break
            h.update(block)

    return h.hexdigest()
