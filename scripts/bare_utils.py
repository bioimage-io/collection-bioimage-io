import hashlib
import json
import os
from typing import Any, Dict, Union

DEPLOYED_BASE_URL = f"https://{os.getenv('GITHUB_REPOSITORY_OWNER', 'bioimage-io')}.github.io/collection-bioimage-io"
RAW_BASE_URL = f"https://raw.githubusercontent.com/{os.getenv('GITHUB_REPOSITORY_OWNER', 'bioimage-io')}/collection-bioimage-io/main"


def set_gh_actions_outputs(outputs: Dict[str, Union[str, Any]]):
    for name, out in outputs.items():
        set_gh_actions_output(name, out)


def set_gh_actions_output(name: str, output: Union[str, Any]):
    """set output of a github actions workflow step calling this script"""
    if isinstance(output, bool):
        output = "yes" if output else "no"

    if not isinstance(output, str):
        output = json.dumps(output, sort_keys=True)

    # escape special characters when setting github actions step output
    output = output.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::set-output name={name}::{output}")


def get_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(h.block_size)
            if not block:
                break
            h.update(block)

    return h.hexdigest()
