import dataclasses
import platform
import sys
from abc import ABC, abstractmethod
from argparse import ArgumentParser
from pathlib import Path
from typing import List, Optional

from marshmallow import ValidationError

from bioimageio import spec
from bioimageio.spec.shared import yaml
from bioimageio.spec.shared.common import nested_default_dict_as_nested_dict

try:
    from bioimageio import core

    raise ImportError  # todo: remove
except ImportError:
    core = None


def parse_args():
    p = ArgumentParser(description="Generate validation summary for a BioImage.IO resource collection")
    p.add_argument("collection_path", type=Path)
    p.add_argument("output_cache_path", type=Path, help="test output to update (only new resources are tested)")

    args = p.parse_args()
    return args


@dataclasses.dataclass
class Key:
    id: str
    py_version: str = platform.python_version()
    spec_version: str = spec.__version__
    core_version: Optional[str] = None if core is None else core.__version__


@dataclasses.dataclass
class Entry:
    source: str  # todo: remove source?
    errors: List[str]


class OutputCacheInterface(ABC):
    @abstractmethod
    def get(self, key: Key) -> Optional[Entry]:
        raise NotImplementedError

    @abstractmethod
    def set(self, key: Key, entry: Entry) -> None:
        raise NotImplementedError

    @abstractmethod
    def write(self) -> None:
        """write output to disk"""
        raise NotImplementedError


class OutputCache(OutputCacheInterface):
    def __init__(self, path: Path):
        self.path = path
        if path.exists():
            self.data = yaml.load(path)
        else:
            self.data = {}

    def get(self, key: Key) -> Optional[Entry]:
        ent = self.data.get(self._key_to_yaml_key(key))
        return None if ent is None else Entry(**ent)

    def set(self, key: Key, entry: Entry) -> None:
        self.data[self._key_to_yaml_key(key)] = dataclasses.asdict(entry)

    @staticmethod
    def _key_to_yaml_key(key: Key) -> str:
        return ",".join(map(str, dataclasses.astuple(key)))

    def write(self) -> None:
        yaml.dump(self.data, self.path)


def get_zenodo_community_rersources(collection_path: Path):
    collection = yaml.load(collection_path)
    return {entry["id"]: entry["source"] for entry in collection["attachments"]["zenodo"]}


def main(collection_path: Path, output_cache_path: Path) -> int:
    output_cache = OutputCache(output_cache_path)
    for id_, source in get_zenodo_community_rersources(collection_path).items():
        key = Key(id_)

        try:
            spec.load_raw_resource_description(source, update_to_current_format=False)
        except ValidationError as e:
            errors = nested_default_dict_as_nested_dict(e.normalized_messages())
        except Exception as e:
            errors = [str(e)]
        else:
            errors = []

        output_cache.set(key, Entry(source, errors))

    output_cache.write()
    return 0


if __name__ == "__main__":
    args = parse_args()
    sys.exit(main(args.collection_path, args.output_cache_path))
