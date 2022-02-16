import shutil
import warnings
from distutils.version import StrictVersion
from pathlib import Path
from typing import Dict, List, Optional, Union

import requests
import typer
from marshmallow import missing
from marshmallow.utils import _Missing

from bare_utils import set_gh_actions_outputs
from bioimageio.spec import load_raw_resource_description, validate
from bioimageio.spec.model.raw_nodes import Model, WeightsFormat
from bioimageio.spec.rdf.raw_nodes import RDF
from bioimageio.spec.shared import yaml
from bioimageio.spec.shared.raw_nodes import Dependencies, URI
from utils import iterate_over_gh_matrix


def get_base_env() -> Dict[str, Union[str, List[Union[str, Dict[str, List[str]]]]]]:
    return {"channels": ["conda-forge", "defaults"], "dependencies": ["bioimageio.core"]}


def get_env_from_deps(deps: Dependencies):
    conda_env = get_base_env()
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
                    raise TypeError(f"expected dependencies in conda environment.yaml to be a list, but got: {deps}")
                if not any(d.startswith("bioimageio.core") for d in deps):
                    conda_env["dependencies"] = deps + ["bioimageio.core"]
            elif deps.manager == "pip":
                pip_req = [d for d in dep_file_content.split("\n") if not d.strip().startswith("#")]
                conda_env["dependencies"].append("pip")
                conda_env["dependencies"].append({"pip": pip_req})
            else:
                raise NotImplementedError(deps.manager)

    except Exception as e:
        warnings.warn(f"Failed to resolve dependencies: {e}")

    return conda_env


def get_version_range(v: StrictVersion) -> str:
    v_major, v_minor, v_patch = v.version
    return f">={v_major}.{v_minor},<{v_major}.{v_minor + 1}"


def get_default_env(
    *,
    opset_version: Optional[int] = None,
    pytorch_version: Optional[StrictVersion] = None,
    tensorflow_version: Optional[StrictVersion] = None,
):
    conda_env = get_base_env()
    if opset_version is not None:
        conda_env["dependencies"].append("onnxruntime")
        # note: we should not need to worry about the opset version,
        # see https://github.com/microsoft/onnxruntime/blob/master/docs/Versioning.md

    if pytorch_version is not None:
        conda_env["channels"].insert(0, "pytorch")
        conda_env["dependencies"].append(f"pytorch {get_version_range(pytorch_version)}")
        conda_env["dependencies"].append("cpuonly")

    if tensorflow_version is not None:
        tf_major, tf_minor, tf_patch = tensorflow_version.version

        # tensorflow 1.15 is not available on conda, so we need to inject this as a pip dependency
        if (tf_major, tf_minor) == (1, 15):
            conda_env["dependencies"].append("pip")
            conda_env["dependencies"].append("python >=3.7,<3.8")  # tf 1.15 not available for py>=3.8
            conda_env["dependencies"].append({"pip": [f"tensorflow {get_version_range(tensorflow_version)}"]})
        else:  # use conda otherwise
            conda_env["dependencies"].append(f"tensorflow {get_version_range(tensorflow_version)}")

    return conda_env


def write_conda_env_file(*, rd: Model, weight_format: WeightsFormat, path: Path, env_name: str):
    assert isinstance(rd, Model)
    given_versions: Dict[str, Union[_Missing, StrictVersion]] = {}
    default_versions = dict(
        pytorch_version=StrictVersion("1.10"), tensorflow_version=StrictVersion("1.15"), opset_version=15
    )
    if weight_format in ["pytorch_state_dict", "torchscript"]:
        given_versions["pytorch_version"] = rd.weights[weight_format].pytorch_version
    elif weight_format in ["tensorflow_saved_model_bundle", "keras_hdf5"]:
        given_versions["tensorflow_version"] = rd.weights[weight_format].tensorflow_version
    elif weight_format in ["onnx"]:
        given_versions["opset_version"] = rd.weights[weight_format].opset_version
    else:
        raise NotImplementedError(weight_format)

    deps = rd.weights[weight_format].dependencies
    if deps is missing:
        conda_env = get_default_env(**{vn: v or default_versions[vn] for vn, v in given_versions.items()})
    else:
        if any(given_versions.values()):
            warnings.warn(f"Using specified dependencies; ignoring given versions: {given_versions}")

        conda_env = get_env_from_deps(deps)

    conda_env["name"] = env_name

    path.parent.mkdir(parents=True, exist_ok=True)
    yaml.dump(conda_env, path)


def ensure_valid_conda_env_name(name: str) -> str:
    for illegal in ("/", " ", ":", "#"):
        name = name.replace(illegal, "")

    return name or "empty"


def prepare_dynamic_test_cases(
    rd: Union[Model, RDF], resource_id: str, version_id: str, dist: Path, rdf_path: Path
) -> List[Dict[str, str]]:
    validation_cases = []
    # construct test cases based on resource type
    if isinstance(rd, Model):
        # add rdf to artifact
        rdf_in_artifact_path = dist / resource_id / version_id / "rdf.yaml"
        rdf_in_artifact_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(rdf_path, rdf_in_artifact_path)

        # generate validation cases per weight format
        for wf in rd.weights:
            # we skip the keras validation for now, see
            # https://github.com/bioimage-io/collection-bioimage-io/issues/16
            if wf == "keras_hdf5":
                warnings.warn("keras weights are currently not validated")
                continue

            env_name = ensure_valid_conda_env_name(version_id)
            write_conda_env_file(
                rd=rd,
                weight_format=wf,
                path=dist / resource_id / version_id / f"conda_env_{wf}.yaml",
                env_name=env_name,
            )
            validation_cases.append(
                {
                    "env_name": env_name,
                    "resource_id": resource_id,
                    "version_id": version_id,
                    "weight_format": wf,
                    "rdf_path": str(rdf_in_artifact_path),
                }
            )
    elif isinstance(rd, RDF):
        pass
    else:
        raise TypeError(rd)

    return validation_cases


def main(
    dist: Path,
    pending_matrix: str,
    rdf_dirs: List[Path] = (
        Path(__file__).parent / "../dist/updated_rdfs/rdfs",
        Path(__file__).parent / "../gh-pages/rdfs",
    ),
):
    dynamic_test_cases = []
    for matrix in iterate_over_gh_matrix(pending_matrix):
        resource_id = matrix["resource_id"]
        version_id = matrix["version_id"]

        for root in rdf_dirs:
            rdf_path = root / resource_id / version_id / "rdf.yaml"
            if rdf_path.exists():
                break
        else:
            raise FileNotFoundError(f"{resource_id}/{version_id}/rdf.yaml in {rdf_dirs}")

        static_summary = validate(rdf_path)

        static_summary_path = dist / resource_id / version_id / "validation_summary_static.yaml"
        static_summary_path.parent.mkdir(parents=True, exist_ok=True)
        yaml.dump(static_summary, static_summary_path)
        if not static_summary["error"]:
            latest_static_summary = validate(rdf_path, update_format=True)
            if not latest_static_summary["error"]:
                rd = load_raw_resource_description(rdf_path, update_to_format="latest")
                assert isinstance(rd, RDF)
                dynamic_test_cases += prepare_dynamic_test_cases(rd, resource_id, version_id, dist, rdf_path=rdf_path)

            if "name" not in latest_static_summary:
                latest_static_summary[
                    "name"
                ] = "bioimageio.spec static validation with auto-conversion to latest format"

            yaml.dump(latest_static_summary, static_summary_path.with_name("validation_summary_latest_static.yaml"))

    out = dict(has_dynamic_test_cases=bool(dynamic_test_cases), dynamic_test_cases={"include": dynamic_test_cases})
    set_gh_actions_outputs(out)
    return out


if __name__ == "__main__":
    typer.run(main)
