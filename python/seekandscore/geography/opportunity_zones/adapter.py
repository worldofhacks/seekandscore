"""Fail-closed reader for the official CDFI 2018 QOZ Shapefile archive."""

import hashlib
import json
import math
import stat
import tempfile
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID

import shapefile

from seekandscore.geography.opportunity_zones.models import (
    DesignationStatus,
    OpportunityZoneTract,
    TemporalPrecision,
)
from seekandscore.geography.opportunity_zones.source import (
    CDFI_QOZ_2018_CENSUS_VINTAGE,
    CDFI_QOZ_2018_EXPECTED_SHA256,
    CDFI_QOZ_2018_EXPECTED_TRACTS,
    CDFI_QOZ_2018_ROUND_ID,
    CDFI_QOZ_2018_SRID,
)

_REQUIRED_MEMBERS = frozenset(
    {
        "8764oz.shp",
        "8764oz.shx",
        "8764oz.dbf",
        "8764oz.prj",
        "Designated QOZs.12.14.18.xlsx",
        "Readme8764.txt",
    }
)
_EXPECTED_FIELDS = ("CENSUSTRAC", "STATENAME", "COUNTYNAME")
_WEB_MERCATOR_LIMIT = 21_000_000.0


class OpportunityZoneArchiveError(ValueError):
    """The archive is unsafe, unreviewed, or violates the official schema contract."""


@dataclass(frozen=True)
class ArchiveSafetyLimits:
    max_members: int = 32
    max_compressed_bytes: int = 64 * 1024 * 1024
    max_uncompressed_bytes: int = 128 * 1024 * 1024
    max_member_bytes: int = 96 * 1024 * 1024
    max_compression_ratio: float = 200.0


_DEFAULT_LIMITS = ArchiveSafetyLimits()


@dataclass(frozen=True)
class Cdfi2018ArchiveDataset:
    """Validated, temporarily extracted archive whose records are read lazily."""

    root: Path
    expected_tracts: int
    artifact_id: UUID
    artifact_sha256: str

    def iter_tracts(self) -> Iterator[OpportunityZoneTract]:
        reader = shapefile.Reader(
            shp=str(self.root / "8764oz.shp"),
            shx=str(self.root / "8764oz.shx"),
            dbf=str(self.root / "8764oz.dbf"),
            encoding="utf-8",
        )
        try:
            field_names = tuple(field[0] for field in reader.fields[1:])
            if field_names != _EXPECTED_FIELDS:
                raise OpportunityZoneArchiveError(
                    f"official DBF fields changed: expected {_EXPECTED_FIELDS}, got {field_names}"
                )
            if len(reader) != self.expected_tracts:
                raise OpportunityZoneArchiveError(
                    f"expected {self.expected_tracts} tract records, found {len(reader)}"
                )

            seen_geoids: set[str] = set()
            yielded = 0
            for shape_record in reader.iterShapeRecords():
                record = shape_record.record.as_dict()
                geoid = str(record.get("CENSUSTRAC", "")).strip()
                if len(geoid) != 11 or not geoid.isdigit():
                    raise OpportunityZoneArchiveError(
                        "CENSUSTRAC must be an 11-character numeric 2010 Census GEOID"
                    )
                if geoid in seen_geoids:
                    raise OpportunityZoneArchiveError(f"duplicate tract GEOID: {geoid}")
                seen_geoids.add(geoid)
                state_name = str(record.get("STATENAME", "")).strip()
                county_name = str(record.get("COUNTYNAME", "")).strip()
                if not state_name or not county_name:
                    raise OpportunityZoneArchiveError(
                        f"tract {geoid} is missing state or county provenance"
                    )
                geometry = _multipolygon_geojson(shape_record.shape)
                is_puerto_rico = state_name == "Puerto Rico"
                yielded += 1
                yield OpportunityZoneTract(
                    round_id=CDFI_QOZ_2018_ROUND_ID,
                    tract_geoid=geoid,
                    census_vintage=CDFI_QOZ_2018_CENSUS_VINTAGE,
                    certification_status=DesignationStatus.TREASURY_CERTIFIED,
                    designation_status=DesignationStatus.EFFECTIVE,
                    effective_from=(date(2017, 12, 22) if is_puerto_rico else date(2018, 1, 1)),
                    effective_from_precision=(
                        TemporalPrecision.EXACT if is_puerto_rico else TemporalPrecision.YEAR
                    ),
                    effective_to=(date(2027, 12, 31) if is_puerto_rico else date(2028, 12, 31)),
                    state_name=state_name,
                    county_name=county_name,
                    source_artifact_id=self.artifact_id,
                    source_artifact_sha256=self.artifact_sha256,
                    geometry_srid=CDFI_QOZ_2018_SRID,
                    geometry_geojson=geometry,
                )
            if yielded != self.expected_tracts or len(seen_geoids) != self.expected_tracts:
                raise OpportunityZoneArchiveError(
                    "archive iteration did not produce the expected unique tract set"
                )
        finally:
            reader.close()


class Cdfi2018ArchiveAdapter:
    """Validate a pinned archive, then expose a lazy tract iterator."""

    def __init__(
        self,
        *,
        expected_sha256: str = CDFI_QOZ_2018_EXPECTED_SHA256,
        expected_tracts: int = CDFI_QOZ_2018_EXPECTED_TRACTS,
        limits: ArchiveSafetyLimits = _DEFAULT_LIMITS,
    ) -> None:
        self.expected_sha256 = expected_sha256
        self.expected_tracts = expected_tracts
        self.limits = limits

    @contextmanager
    def open_archive(
        self,
        content: bytes,
        *,
        artifact_id: UUID,
    ) -> Iterator[Cdfi2018ArchiveDataset]:
        if len(content) > self.limits.max_compressed_bytes:
            raise OpportunityZoneArchiveError("archive exceeds the compressed byte limit")
        sha256 = hashlib.sha256(content).hexdigest()
        if sha256 != self.expected_sha256:
            raise OpportunityZoneArchiveError("archive SHA-256 does not match the reviewed source")

        with tempfile.TemporaryDirectory(prefix="seekandscore-qoz-") as temporary:
            root = Path(temporary).resolve()
            try:
                with zipfile.ZipFile(_bytes_reader(content)) as archive:
                    members = _validate_members(archive, self.limits)
                    _extract_required_members(archive, members, root, self.limits)
            except zipfile.BadZipFile as error:
                raise OpportunityZoneArchiveError("artifact is not a valid ZIP archive") from error

            projection = (root / "8764oz.prj").read_text(encoding="utf-8-sig")
            if "WGS_1984_Web_Mercator_Auxiliary_Sphere" not in projection:
                raise OpportunityZoneArchiveError("official projection changed from EPSG:3857")

            yield Cdfi2018ArchiveDataset(
                root=root,
                expected_tracts=self.expected_tracts,
                artifact_id=artifact_id,
                artifact_sha256=sha256,
            )


def _bytes_reader(content: bytes) -> Any:
    from io import BytesIO

    return BytesIO(content)


def _validate_members(
    archive: zipfile.ZipFile,
    limits: ArchiveSafetyLimits,
) -> dict[str, zipfile.ZipInfo]:
    infos = archive.infolist()
    if not infos or len(infos) > limits.max_members:
        raise OpportunityZoneArchiveError("archive member count is outside the approved limit")

    members: dict[str, zipfile.ZipInfo] = {}
    total_uncompressed = 0
    for info in infos:
        path = PurePosixPath(info.filename)
        if (
            not info.filename
            or path.is_absolute()
            or ".." in path.parts
            or "\\" in info.filename
            or len(path.parts) != 1
        ):
            raise OpportunityZoneArchiveError("archive contains an unsafe or nested member path")
        normalized = info.filename.casefold()
        if normalized in members:
            raise OpportunityZoneArchiveError("archive contains duplicate member names")
        unix_mode = info.external_attr >> 16
        if unix_mode and stat.S_ISLNK(unix_mode):
            raise OpportunityZoneArchiveError("archive symbolic links are not allowed")
        if info.flag_bits & 0x1:
            raise OpportunityZoneArchiveError("encrypted archive members are not allowed")
        if info.file_size > limits.max_member_bytes:
            raise OpportunityZoneArchiveError("archive member exceeds its byte limit")
        total_uncompressed += info.file_size
        if total_uncompressed > limits.max_uncompressed_bytes:
            raise OpportunityZoneArchiveError("archive exceeds the uncompressed byte limit")
        if info.file_size:
            if info.compress_size <= 0:
                raise OpportunityZoneArchiveError("archive member has an invalid compressed size")
            if info.file_size / info.compress_size > limits.max_compression_ratio:
                raise OpportunityZoneArchiveError("archive member exceeds compression-ratio limit")
        members[normalized] = info

    missing = sorted(name for name in _REQUIRED_MEMBERS if name.casefold() not in members)
    if missing:
        raise OpportunityZoneArchiveError(f"archive is missing required members: {missing}")
    return members


def _extract_required_members(
    archive: zipfile.ZipFile,
    members: dict[str, zipfile.ZipInfo],
    root: Path,
    limits: ArchiveSafetyLimits,
) -> None:
    for expected_name in _REQUIRED_MEMBERS:
        info = members[expected_name.casefold()]
        target = (root / expected_name).resolve()
        if not target.is_relative_to(root):
            raise OpportunityZoneArchiveError("archive member escapes extraction directory")
        written = 0
        with archive.open(info) as source, target.open("xb") as destination:
            while chunk := source.read(1024 * 1024):
                written += len(chunk)
                if written > info.file_size or written > limits.max_member_bytes:
                    raise OpportunityZoneArchiveError(
                        "archive member expanded beyond declared limits"
                    )
                destination.write(chunk)
        if written != info.file_size:
            raise OpportunityZoneArchiveError("archive member size differs from its declaration")


def _multipolygon_geojson(shape: Any) -> str:
    if shape.shapeType not in {shapefile.POLYGON, shapefile.POLYGONM, shapefile.POLYGONZ}:
        raise OpportunityZoneArchiveError("tract geometry is not a polygon")
    try:
        source = shape.__geo_interface__
    except Exception as error:
        raise OpportunityZoneArchiveError("tract geometry cannot be decoded") from error
    geometry_type = source.get("type")
    coordinates = source.get("coordinates")
    if geometry_type == "Polygon":
        coordinates = [coordinates]
    elif geometry_type != "MultiPolygon":
        raise OpportunityZoneArchiveError("tract geometry is not Polygon or MultiPolygon")
    _validate_coordinates(coordinates)
    try:
        return json.dumps(
            {"type": "MultiPolygon", "coordinates": coordinates},
            allow_nan=False,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as error:
        raise OpportunityZoneArchiveError("tract geometry contains invalid coordinates") from error


def _validate_coordinates(value: Any) -> None:
    if not isinstance(value, (list, tuple)) or not value:
        raise OpportunityZoneArchiveError("tract geometry has empty coordinates")
    stack: list[Any] = [value]
    numeric_count = 0
    while stack:
        item = stack.pop()
        if isinstance(item, (list, tuple)):
            if not item:
                raise OpportunityZoneArchiveError("tract geometry has an empty ring")
            stack.extend(item)
            continue
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise OpportunityZoneArchiveError("tract geometry has a non-numeric coordinate")
        coordinate = float(item)
        if not math.isfinite(coordinate) or abs(coordinate) > _WEB_MERCATOR_LIMIT:
            raise OpportunityZoneArchiveError("tract coordinate is outside EPSG:3857 bounds")
        numeric_count += 1
    if numeric_count < 8:
        raise OpportunityZoneArchiveError("tract geometry has too few coordinates")
