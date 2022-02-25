import subprocess
from pprint import pprint

import typer

from bare_utils import set_gh_actions_output


def main(prefix: str):
    subprocess.run(["git", "fetch"])
    remote_branch_proc = subprocess.run(["git", "branch", "-r"], capture_output=True, text=True)
    remote_branches = [
        rb[len(f"origin/{prefix}") :] for rb in remote_branch_proc.stdout.split() if rb.startswith(f"origin/{prefix}")
    ]
    print(f"Found remote {prefix} branches of:")
    pprint(remote_branches)

    set_gh_actions_output("branches", ",".join(remote_branches))


if __name__ == "__main__":
    typer.run(main)
