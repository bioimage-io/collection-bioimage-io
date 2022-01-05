import subprocess
from pprint import pprint

import typer

from utils import set_gh_actions_output


def main():
    subprocess.run(["git", "fetch"])
    remote_branch_proc = subprocess.run(["git", "branch", "-r"], capture_output=True, text=True)
    remote_branches = [
        rb[len("origin/auto-update-") :]
        for rb in remote_branch_proc.stdout.split()
        if rb.startswith("origin/auto-update-")
    ]
    print("Found remote auto-update branches of:")
    pprint(remote_branches)

    set_gh_actions_output("auto-update-branches", ",".join(remote_branches))


if __name__ == "__main__":
    typer.run(main)
