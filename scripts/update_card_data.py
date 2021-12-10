import json
import warnings
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union

import typer
from boltons.iterutils import remap
from marshmallow import missing
from ruamel.yaml import YAML

from bioimageio.core import load_raw_resource_description

yaml = YAML(typ="safe")


PASSED_DYNAMIC_VALIDATION = "passed_dynamic_validation"  # static and dynamic checks all passed
PASSED_DYNAMIC_VALIDATION_PARTIALLY = "passed_dynamic_validation_partially"  # static and some dynamic checks passed
FAILED_DYNAMIC_VALIDATION = "failed_dynamic_validation"
NO_DYNAMIC_VALIDATION = "no_dynamic_validation"  # no dynamic checks exist for this resource type
PASSED_STATIC_VALIDATION = "passed_static_validation"
FAILED_STATIC_VALIDATION = "failed_static_validation"

SPECIAL_TAGS = (
    PASSED_DYNAMIC_VALIDATION,
    PASSED_DYNAMIC_VALIDATION_PARTIALLY,
    FAILED_DYNAMIC_VALIDATION,
    NO_DYNAMIC_VALIDATION,
    PASSED_STATIC_VALIDATION,
    FAILED_STATIC_VALIDATION,
)

UNKNOWN = "unknown"


@dataclass
class VersionCard:
    authors: List[dict]
    created: datetime
    format_version: str
    license: str
    maintainers: List[dict]
    name: str
    tags: List[str]
    type: str
    validation_summary: dict
    version_id: str
    version_doi: Optional[str]
    description: str
    documentation: str
    stats: Dict[str, Union[int, float]]
    source: str
    covers: List[str]
    links: List[str]

    def as_concept_card(self, id_: str, concept_doi: Optional[str], previous_versions: List["VersionCard"]):
        return ConceptCard(id=id_, concept_doi=concept_doi, previous_versions=previous_versions, **asdict(self))


@dataclass
class ConceptCard(VersionCard):
    id: str
    concept_doi: Optional[str]
    previous_versions: List[VersionCard]  # newest first

    @classmethod
    def load(cls, path: Path):
        data = yaml.load(path)
        data["previous_versions"] = [VersionCard(**pv) for pv in data["previous_versions"]]
        return cls(**data)

    def save(self, path: Path):
        data = asdict(self)
        yaml.dump(data, path)

    def as_version_card(self) -> VersionCard:
        data = asdict(self)
        data.pop("id")
        data.pop("previous_versions")
        return VersionCard(**data)


def _add_to_tag_set(tags: set, validation_summary: dict):
    if "static" not in validation_summary:
        # nested validation summaries
        for group, val_summary in validation_summary.items():
            _add_to_tag_set(tags, val_summary)
    else:
        if validation_summary["static"]["success"]:
            tags.add(PASSED_STATIC_VALIDATION)
        else:
            tags.add(FAILED_STATIC_VALIDATION)

        if "dynamic" in validation_summary:
            if validation_summary["dynamic"]["success"]:
                tags.add(PASSED_DYNAMIC_VALIDATION)
            else:
                tags.add(FAILED_DYNAMIC_VALIDATION)
        else:
            tags.add(NO_DYNAMIC_VALIDATION)


def get_special_tags(validation_summary: dict):
    tags = set()
    _add_to_tag_set(tags, validation_summary)
    if all(st in tags for st in [PASSED_STATIC_VALIDATION, FAILED_STATIC_VALIDATION]):
        warnings.warn("How did we get passed and failed static validation?? should always be the same!")
        tags.remove(PASSED_STATIC_VALIDATION)

    if all(st in tags for st in [FAILED_DYNAMIC_VALIDATION, PASSED_DYNAMIC_VALIDATION]):
        tags.remove(FAILED_DYNAMIC_VALIDATION)
        tags.remove(PASSED_DYNAMIC_VALIDATION)
        tags.add(PASSED_DYNAMIC_VALIDATION_PARTIALLY)

    if (
        any(
            st in tags
            for st in [PASSED_DYNAMIC_VALIDATION_PARTIALLY, FAILED_DYNAMIC_VALIDATION, PASSED_DYNAMIC_VALIDATION]
        )
        and NO_DYNAMIC_VALIDATION in tags
    ):
        tags.remove(NO_DYNAMIC_VALIDATION)

    return list(tags)


def make_version_card(
    summaries_folder: Path, new_resources_folder: Path, *, doi: Optional[str] = None, version_id: Optional[str] = None
):
    assert doi or version_id
    hit = yaml.load(new_resources_folder / doi / "hit.yaml")
    # get (combined) validation summary
    # potentially multiple validation summaries (e.g. for model rdf per weight format)
    validation_summary = {
        p.name.replace("_validation_summary.yaml", ""): yaml.load(p)
        for p in (summaries_folder / doi).glob("*validation_summary.yaml")
    }
    if "validation_summary.yaml" in validation_summary:
        # single validation summary (e.g. for general rdf)
        assert len(validation_summary) == 1
        validation_summary = validation_summary["validation_summary.yaml"]

    # obtain other card fields
    try:
        rd = asdict(load_raw_resource_description(doi))

        # replace Marshmallow missing values
        rd = remap(rd, lambda p, k, v: (k, "missing" if v is missing else v))

        authors = rd.get("authors", [])
        covers = rd.get("covers", [])
        description = rd.get("description", UNKNOWN)
        documentation = rd.get("documentation", UNKNOWN)
        format_version = rd.get("format_version", UNKNOWN)
        license_ = rd.get("license", UNKNOWN)
        links = rd.get("links", [])
        maintainers = rd.get("maintainers", [])
        name = rd.get("name", UNKNOWN)
        source = str(rd.get("root_path", UNKNOWN))
        tags = rd.get("tags", [])
        type_ = rd.get("type", UNKNOWN)
    except Exception as e:
        warnings.warn(str(e))
        authors = []
        covers = []
        description = UNKNOWN
        documentation = UNKNOWN
        format_version = UNKNOWN
        license_ = UNKNOWN
        links = []
        maintainers = []
        name = doi or version_id
        source = doi or version_id
        tags = []
        type_ = "rdf"

    # set special tags
    tags = [t for t in tags if t not in SPECIAL_TAGS] + get_special_tags(validation_summary)

    return VersionCard(
        authors=authors,
        covers=covers,
        created=datetime.fromisoformat(hit["created"]),
        description=description,
        documentation=documentation,
        format_version=format_version,
        license=license_,
        links=links,
        maintainers=maintainers,
        name=name,
        source=source,
        stats=hit["stats"],
        tags=tags,
        type=type_,
        validation_summary=validation_summary,
        version_doi=doi,
        version_id=version_id,
    )


def main(
    collection_folder: Path,
    id_: str,
    new_version_ids: str = typer.Argument(..., help="json string of list of dois"),
    summaries_folder: Path = typer.Argument(...),
    new_resources_folder: Path = typer.Argument(...),
) -> int:
    new_version_ids = json.loads(new_version_ids)

    card_path = collection_folder / id_ / "card.yaml"
    if card_path.exists():
        try:
            card = ConceptCard.load(card_path)
        except Exception as e:
            warnings.warn(f"encountered invalid card at {card_path}: {e}")
            versions = []
        else:
            versions = card.previous_versions
            versions.append(card.as_version_card())
            versions = [v for v in versions if v.version_id not in new_version_ids]
    else:
        versions = []

    concept_path = collection_folder / id_ / "concept.yaml"
    assert concept_path.exists(), concept_path
    concept = yaml.load(concept_path)

    for cv in concept["versions"]:
        if cv["version_id"] in new_version_ids:
            versions.append(
                make_version_card(
                    summaries_folder, new_resources_folder, version_id=cv["version_id"], doi=cv.get("doi")
                )
            )

    versions = sorted(versions, key=lambda vc: vc.created)
    latest_version = versions.pop()
    card = latest_version.as_concept_card(id_, concept.get("concept_doi"), versions[::-1])
    card.save(card_path)
    return 0


if __name__ == "__main__":
    typer.run(main)
