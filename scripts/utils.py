import json
from typing import Any, Union


def set_gh_actions_output(name: str, output: Union[str, Any]):
    """set output of a github actions workflow step calling this script"""
    if not isinstance(output, str):
        output = json.dumps(output)

    # escape special characters when setting github actions step output
    output = output.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::set-output name={name}::{output}")
