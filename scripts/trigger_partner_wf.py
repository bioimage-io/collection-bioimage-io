from pprint import pprint

import typer
from github import Github


def main(
    pending_matrix: str,
    *,
    owner: str = "ilastik",
    repo: str = "bioimage-io-resources",
    workflow: str = "test_bioimageio_resources.yaml",
    pat: str = None,
):
    inputs = dict(pending_matrix=pending_matrix)
    ref = "main"
    pprint(inputs)
    g = Github(login_or_token=pat)
    repo = g.get_repo(f"{owner}/{repo}")
    wf = repo.get_workflow(workflow)
    success = wf.create_dispatch(ref, inputs=inputs)
    print("success" if success else "failed")


if __name__ == "__main__":
    typer.run(main)
