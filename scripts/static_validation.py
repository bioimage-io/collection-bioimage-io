import json
import warnings
from pathlib import Path
from typing import Dict, List, Union

import requests
import typer
from ruamel.yaml import YAML

from bioimageio.spec import load_raw_resource_description, validate
from bioimageio.spec.model.raw_nodes import Model
from bioimageio.spec.rdf.raw_nodes import RDF
from bioimageio.spec.shared.raw_nodes import URI

yaml = YAML(typ="safe")


def set_gh_actions_output(name: str, output: str):
    """set output of a github actions workflow step calling this script"""
    # escape special characters when setting github actions step output
    output = output.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::set-output name={name}::{output}")


def write_conda_env_file(*, rd: Model, weight_format: str, path: Path, env_name: str):
    # minimal env for invalid model rdf to be checked with bioimageio.spec for validation errors only
    minimal_conda_env: Dict[str, List[Union[str, Dict[str, List[str]]]]] = {
        "channels": ["conda-forge", "defaults"],
        "dependencies": ["bioimageio.core"],
    }
    conda_env = dict(minimal_conda_env)
    if isinstance(rd, Model):
        if weight_format in ["pytorch_state_dict"]:  # weights with specified dependencies field
            try:
                # planned future version:
                deps = rd.weights["pytorch_state_dict"].dependencies
            except AttributeError:
                # current version (0.4.0)
                deps = rd.dependencies

            try:
                if deps.manager in ["conda", "pip"]:
                    if isinstance(deps.file, Path):
                        raise TypeError(f"File path for remote source? {deps.file} should be a url")
                    elif not isinstance(deps.file, URI):
                        raise TypeError(deps.file)

                    r = requests.get(str(deps.file))
                    r.raise_for_status()
                    dep_file_content = r.text
                    if deps.manager == "conda":
                        conda_env = yaml.load(dep_file_content)
                        # add bioimageio.core if not present
                        channels = conda_env.get("channels", [])
                        if "conda-forge" not in channels:
                            conda_env["channels"] = channels + ["conda-forge"]

                        deps = conda_env.get("dependencies", [])
                        if not isinstance(deps, list):
                            raise TypeError(
                                f"expected dependencies in conda environment.yaml to be a list, but got: {deps}"
                            )
                        if not any(d.startswith("bioimageio.core") for d in deps):
                            conda_env["dependencies"] = deps + ["bioimageio.core"]
                    elif deps.manager == "pip":
                        pip_req = [d for d in dep_file_content.split("\n") if not d.strip().startswith("#")]
                        conda_env["dependencies"].append("bioimageio.core")
                        conda_env["dependencies"].append("pip")
                        conda_env["dependencies"].append({"pip": pip_req})
                    else:
                        raise NotImplementedError(deps.manager)

            except Exception as e:
                warnings.warn(f"Failed to resolve weight dependencies: {e}")
                conda_env = dict(minimal_conda_env)

        elif weight_format == "torchscript":
            conda_env["channels"].insert(0, "pytorch")
            conda_env["dependencies"].append("pytorch")
            conda_env["dependencies"].append("cpuonly")
            # todo: pin pytorch version for torchscript (add version to torchscript weight spec)
        elif weight_format == "tensorflow_saved_model_bundle":
            tf_version = rd.weights["tensorflow_saved_model_bundle"].tensorflow_version
            if not tf_version:
                # todo: document default tf version
                tf_version = "1.15"
            conda_env["dependencies"].append(f"pip")
            conda_env["dependencies"].append({"pip": [f"tensorflow=={tf_version}"]})
        elif weight_format == "keras_hdf5":
            tf_version = rd.weights["keras_hdf5"].tensorflow_version
            if not tf_version:
                # todo: document default tf version
                tf_version = "1.15"
            conda_env["dependencies"].append(f"pip")
            conda_env["dependencies"].append({"pip": [f"tensorflow=={tf_version}"]})
        elif weight_format == "onnx":
            conda_env["dependencies"].append("onnxruntime")
            # note: we should not need to worry about the opset version,
            # see https://github.com/microsoft/onnxruntime/blob/master/docs/Versioning.md
        else:
            warnings.warn(f"Unknown weight format '{weight_format}'")
            # todo: add weight formats

    else:
        TypeError(rd)

    conda_env["name"] = env_name

    path.parent.mkdir(parents=True, exist_ok=True)
    yaml.dump(conda_env, path)


def ensure_valid_conda_env_name(name: str) -> str:
    for illegal in ("/", " ", ":", "#"):
        name = name.replace(illegal, "")

    return name or "empty"


def prepare_dynamic_test_cases(rd: Union[Model, RDF], version_id: str, resource_folder: Path) -> List[Dict[str, str]]:
    validation_cases = []
    # construct test cases based on resource type
    if isinstance(rd, Model):
        # generate validation cases per weight format
        for wf in rd.weights:
            env_name = ensure_valid_conda_env_name(version_id)
            write_conda_env_file(
                rd=rd, weight_format=wf, path=resource_folder / version_id / f"conda_env_{wf}.yaml", env_name=env_name
            )
            validation_cases.append({"env_name": env_name, "version_id": version_id, "weight_format": wf})
    elif isinstance(rd, RDF):
        pass
    else:
        raise TypeError(rd)

    return validation_cases


def main(collection_folder: Path, branch: str, resource_folder: Path, version_id: str) -> int:
    if branch.startswith("auto-update-"):
        resource_id = branch[len("auto-update-") :]
    else:
        warnings.warn(f"called with non-auto-update branch {branch}")
        return 0

    resource_path = collection_folder / resource_id / "resource.yaml"
    resource = yaml.load(resource_path)

    for v in resource["versions"]:
        if v["version_id"] == version_id:
            source = v["source"]
            break
    else:
        raise RuntimeError(f"version_id {version_id} not found in {resource_path}")

    static_summary = validate(source)
    static_summary["name"] = "bioimageio.spec static validation"
    static_summary_path = resource_folder / version_id / "validation_summary_static.yaml"
    static_summary_path.parent.mkdir(parents=True, exist_ok=True)
    yaml.dump(static_summary, static_summary_path)
    if static_summary["error"]:
        passed_static = "no"
        passed_latest_static = "no"
        dynamic_test_cases = []
    else:
        passed_static = "yes"
        latest_static_summary = validate(source, update_format=True)
        if latest_static_summary["error"]:
            passed_latest_static = "no"
            dynamic_test_cases = []
        else:
            passed_latest_static = "yes"
            rd = load_raw_resource_description(source, update_to_format="latest")
            assert isinstance(rd, RDF)
            dynamic_test_cases = prepare_dynamic_test_cases(rd, version_id, resource_folder)

        latest_static_summary["name"] = "bioimageio.spec static validation with auto-conversion to latest format"

        yaml.dump(latest_static_summary, static_summary_path.with_name("validation_summary_latest_static.yaml"))

    set_gh_actions_output("passed_static", passed_static)
    set_gh_actions_output("has_dynamic_test_cases", passed_latest_static and dynamic_test_cases)
    set_gh_actions_output("dynamic_test_cases", json.dumps({"case": dynamic_test_cases}))

    return 0


if __name__ == "__main__":
    typer.run(main)
