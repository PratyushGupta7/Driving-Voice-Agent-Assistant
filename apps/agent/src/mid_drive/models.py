from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


Category = Literal["coffee", "fuel", "pharmacy"]
AmenityState = Literal["yes", "no", "unknown"]
PreferAlong = Literal["start", "end"]
InquireKind = Literal["why", "eta", "parking", "other", "compare", "hours", "where"]
PatchOp = Literal[
    "create",
    "add",
    "replace",
    "cancel",
    "unrelated",
    "ambiguous",
    "confirm",
    "next",
    "select",
    "inquire",
]
MissionStatus = Literal["active", "clarifying", "cancelled"]


class SessionPrefs(BaseModel):
    parking_required: bool | None = None
    avoid_tolls: bool | None = None


class MissionConstraints(BaseModel):
    category: Category
    maximum_detour_minutes: int | None = None
    parking_required: bool = False
    avoid_tolls: bool = False
    landmark_query: str | None = None
    destination_query: str | None = None
    origin_query: str | None = None
    brand_query: str | None = None
    prefer_along: PreferAlong | None = None


class MissionPatch(BaseModel):
    operation: PatchOp
    category: Category | None = None
    maximum_detour_minutes: int | None = None
    parking_required: bool | None = None
    avoid_tolls: bool | None = None
    landmark_query: str | None = None
    destination_query: str | None = None
    origin_query: str | None = None
    brand_query: str | None = None
    prefer_along: PreferAlong | None = None
    select_index: int | None = None
    select_name: str | None = None
    inquire_kind: InquireKind | None = None
    clarification_question: str | None = None
    applied_session_pref: bool = False


class OutputGate(str, Enum):
    OPEN = "open"
    CLOSED_FOR_INPUT = "closed_for_input"
    CLOSED_FOR_ERROR = "closed_for_error"
    CLOSED_FOR_END = "closed_for_end"


class FenceDecision(str, Enum):
    ACCEPTED = "accepted"
    STALE_REJECTED = "stale_rejected"
    FAILED = "failed"


@dataclass(frozen=True)
class WorkToken:
    session_id: str
    mission_id: str
    mission_version: int
    output_epoch: int
    input_sequence: int
    request_id: str
    request_kind: str


class ReduceResult(BaseModel):
    changed: bool
    constraints: MissionConstraints | None = None
    status: MissionStatus = "active"
    acknowledgement: str | None = None
    speak_now: bool = False
    replan: bool = False
    select_index: int | None = None
    select_name: str | None = None
    inquire_kind: InquireKind | None = None


class PlaceCandidate(BaseModel):
    id: str = ""
    name: str
    area: str
    category: Category
    parking: AmenityState = "unknown"
    detour_minutes: int | None = None
    lat: float | None = None
    lng: float | None = None
    provenance: str = "fixture"
    fixture_version: str = "gurgaon-delhi-v1"
    distance_to_route_m: float | None = None
    verified: bool = False
    reasons: list[str] = Field(default_factory=list)
    opening_hours: str | None = None
    brand: str | None = None
    operator: str | None = None
    progress: float | None = None
    extra_vs_baseline_s: int | None = None


class RouteSnapshot(BaseModel):
    origin_name: str = "Cyber Hub, Gurugram"
    destination_name: str = "Connaught Place, Delhi"
    origin_lat: float = 28.4947
    origin_lng: float = 77.0883
    dest_lat: float = 28.6315
    dest_lng: float = 77.2167
    geometry: list[list[float]] = Field(default_factory=list)
    via_geometry: list[list[float]] = Field(default_factory=list)
    duration_s: int | None = None
    distance_m: int | None = None
    eta_minutes: int | None = None
    distance_km: float | None = None
    avoid_tolls: bool = False
    provider: str = "fixture"
    origin_query: str = ""
    dest_query: str = ""
    settings_hash: str = "driving"
    toll_compare_minutes: int | None = None
    summary: str = ""


class VersionEntry(BaseModel):
    version: int
    summary: str
    epoch: int


class OperationResult(BaseModel):
    token: WorkToken
    operation_id: str
    provider: str
    candidate: PlaceCandidate | None = None
    route: RouteSnapshot | None = None
    alternatives: list[PlaceCandidate] = Field(default_factory=list)
    error: str | None = None
    delay_ms: int = 0
    fallback_used: bool = False


class MissionSnapshot(BaseModel):
    session_id: str
    mission_id: str | None = None
    mission_version: int = 0
    output_epoch: int = 0
    output_gate: OutputGate = OutputGate.CLOSED_FOR_INPUT
    status: MissionStatus | Literal["idle"] = "idle"
    constraints: MissionConstraints | None = None
    selected: PlaceCandidate | None = None
    alternatives: list[PlaceCandidate] = Field(default_factory=list)
    latest_request_id: dict[str, str] = Field(default_factory=dict)
    geo_mode: str = "fixture"
    rejected_ids: list[str] = Field(default_factory=list)
    version_log: list[VersionEntry] = Field(default_factory=list)
    last_revision: str | None = None
    last_barrier_ms: int | None = None
    route: RouteSnapshot | None = None
    prefs: SessionPrefs = Field(default_factory=SessionPrefs)


@dataclass
class SearchIntent:
    skip_ids: set[str] = field(default_factory=set)


def constraint_brief(constraints: MissionConstraints | None) -> str:
    if constraints is None:
        return "idle"
    bits = [constraints.category]
    if constraints.parking_required:
        bits.append("parking")
    if constraints.avoid_tolls:
        bits.append("no tolls")
    if constraints.maximum_detour_minutes is not None:
        bits.append(f"≤{constraints.maximum_detour_minutes}m")
    if constraints.landmark_query:
        bits.append(f"near {constraints.landmark_query}")
    if constraints.brand_query:
        bits.append(constraints.brand_query)
    if constraints.prefer_along:
        bits.append(constraints.prefer_along)
    return " · ".join(bits)


def needs_new_route(old: MissionConstraints | None, new: MissionConstraints | None) -> bool:
    if new is None:
        return False
    if old is None:
        return True
    return (
        old.avoid_tolls != new.avoid_tolls
        or old.destination_query != new.destination_query
        or old.origin_query != new.origin_query
    )


def needs_new_places(old: MissionConstraints | None, new: MissionConstraints | None) -> bool:
    if new is None:
        return False
    if old is None or needs_new_route(old, new):
        return True
    return old.category != new.category
