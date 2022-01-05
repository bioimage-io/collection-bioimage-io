import json
from itertools import product
from typing import Any, Dict, List, Union


def set_gh_actions_outputs(outputs: Dict[str, Union[str, Any]]):
    for name, out in outputs.items():
        set_gh_actions_output(name, out)


def set_gh_actions_output(name: str, output: Union[str, Any]):
    """set output of a github actions workflow step calling this script"""
    if isinstance(output, bool):
        output = "yes" if output else "no"

    if not isinstance(output, str):
        output = json.dumps(output)

    # escape special characters when setting github actions step output
    output = output.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::set-output name={name}::{output}")


def iterate_over_gh_marix(matrix: Dict[str, list]):
    keys = list(matrix)
    for vals in product(*[matrix[k] for k in keys]):
        yield dict(zip(keys, vals))
