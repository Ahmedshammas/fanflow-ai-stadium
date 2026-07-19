from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import sqrt
from threading import RLock
from typing import Literal
import hashlib


UNIT_METERS = 8


def stable_int(seed: str) -> int:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Point:
    x: int
    y: int


@dataclass(frozen=True)
class Gate:
    gate_id: str
    name: str
    coordinate: Point
    accessible: bool
    ticket_categories: tuple[str, ...]
    notes: str


@dataclass(frozen=True)
class Section:
    section_id: str
    name: str
    coordinate: Point
    accessible: bool
    ticket_categories: tuple[str, ...]
    nearest_gate_id: str
    notes: str


@dataclass(frozen=True)
class Concession:
    stall_id: str
    name: str
    coordinate: Point
    menu_tags: tuple[str, ...]
    accessible: bool
    base_wait_minutes: int
    peak_factor: float
    notes: str


@dataclass
class CleaningCrew:
    crew_id: str
    zone: str
    specialization: tuple[str, ...]
    current_location: Point
    status: Literal["available", "en_route",
                    "cleaning", "paused"] = "available"
    current_assignment: str | None = None
    last_updated: datetime = field(default_factory=now_utc)


@dataclass
class AlertState:
    level: Literal["green", "yellow", "amber", "red", "black"]
    active_incidents: list[dict]
    public_message: str
    last_updated: datetime = field(default_factory=now_utc)


@dataclass(frozen=True)
class IncidentRecord:
    incident_id: str
    incident_type: str
    report: str
    location: Point
    severity: Literal["low", "medium", "high", "critical"]
    created_at: datetime


def euclidean_distance(a: Point, b: Point) -> float:
    return sqrt(((a.x - b.x) ** 2) + ((a.y - b.y) ** 2))


def distance_meters(a: Point, b: Point) -> float:
    return euclidean_distance(a, b) * UNIT_METERS


def cardinal_steps(origin: Point, destination: Point, accessible: bool) -> list[str]:
    dx = destination.x - origin.x
    dy = destination.y - origin.y
    walking_speed = 60 if accessible else 78
    steps: list[str] = []

    if dx:
        direction = "east" if dx > 0 else "west"
        steps.append(f"Walk {abs(dx) * UNIT_METERS} meters {direction}.")
    if dy:
        direction = "north" if dy > 0 else "south"
        steps.append(f"Continue {abs(dy) * UNIT_METERS} meters {direction}.")
    if not steps:
        steps.append("You are already at the destination.")
    if accessible:
        steps.append(
            "Use the accessible corridor and ramp signage throughout the route.")
    estimated_minutes = max(
        1, round(distance_meters(origin, destination) / walking_speed))
    steps.append(f"Estimated walking time: {estimated_minutes} minutes.")
    return steps


def resolve_category_alias(ticket_category: str) -> str:
    normalized = ticket_category.strip().lower()
    aliases = {
        "vip": "vip",
        "premium": "premium",
        "general": "general",
        "standard": "general",
        "family": "family",
        "wheelchair": "accessible",
        "accessibility": "accessible",
        "accessible": "accessible",
        "hospitality": "hospitality",
    }
    return aliases.get(normalized, normalized)


def incident_type_from_text(report: str, severity_hint: str | None = None) -> tuple[str, str]:
    normalized = report.lower()
    severity = (severity_hint or "").strip().lower()

    if any(word in normalized for word in ["spill", "liquid", "slip", "trash", "debris"]):
        return "cleaning_spill", severity or "medium"
    if any(word in normalized for word in ["bottleneck", "crowd", "jam", "congestion", "blocked"]):
        return "crowd_bottleneck", severity or "high"
    if any(word in normalized for word in ["medical", "injury", "collapse", "unconscious"]):
        return "medical", severity or "critical"
    if any(word in normalized for word in ["security", "fight", "argument", "theft"]):
        return "security", severity or "high"
    return "general_ops", severity or "low"


class StadiumDatabase:
    def __init__(self) -> None:
        self.lock = RLock()
        self.gates: dict[str, Gate] = {
            "gate-a": Gate("gate-a", "Gate A - North Plaza", Point(2, 14), True, ("general", "premium", "vip", "family"), "Primary family and general admission entry."),
            "gate-b": Gate("gate-b", "Gate B - Transit Plaza", Point(8, 13), True, ("general", "premium", "vip"), "Closest to the transit drop-off lane."),
            "gate-c": Gate("gate-c", "Gate C - Accessible Entry", Point(13, 13), True, ("general", "premium", "vip", "accessible", "family"), "Wide accessible lanes and ramp access."),
            "gate-d": Gate("gate-d", "Gate D - East Club", Point(18, 12), True, ("premium", "vip", "hospitality"), "Club and hospitality priority entry."),
            "gate-e": Gate("gate-e", "Gate E - South Fan Zone", Point(4, 4), True, ("general", "family"), "Closest to the fan festival space."),
            "gate-f": Gate("gate-f", "Gate F - Service Access", Point(10, 3), False, ("operations", "staff"), "Staff and logistics only."),
            "gate-g": Gate("gate-g", "Gate G - West Terrace", Point(15, 4), True, ("general", "premium", "vip", "accessible"), "Balanced access to the west concourse."),
            "gate-h": Gate("gate-h", "Gate H - Media / VIP", Point(20, 7), True, ("vip", "hospitality"), "Fast lane for VIP and media guests."),
        }

        self.sections: dict[str, Section] = {
            "section-101": Section("section-101", "Section 101", Point(4, 11), True, ("general", "family"), "gate-a", "Lower bowl family seating."),
            "section-102": Section("section-102", "Section 102", Point(6, 10), True, ("general", "premium"), "gate-b", "Main lower bowl general seating."),
            "section-201": Section("section-201", "Section 201", Point(12, 11), True, ("premium", "vip"), "gate-c", "Premium sideline seating."),
            "section-202": Section("section-202", "Section 202", Point(15, 10), True, ("vip", "hospitality"), "gate-d", "Hospitality and lounge access."),
            "section-203": Section("section-203", "Section 203", Point(17, 9), True, ("vip",), "gate-h", "Upper VIP east side."),
            "section-301": Section("section-301", "Section 301", Point(5, 7), True, ("general", "family", "accessible"), "gate-e", "Accessible family concourse access."),
            "section-302": Section("section-302", "Section 302", Point(9, 7), True, ("general", "premium", "accessible"), "gate-c", "Accessible mid-field vantage point."),
            "section-303": Section("section-303", "Section 303", Point(14, 7), True, ("premium", "vip", "accessible"), "gate-g", "Premium accessible west side."),
            "section-401": Section("section-401", "Section 401", Point(11, 4), False, ("operations",), "gate-f", "Operations-only section."),
        }

        self.concessions: dict[str, Concession] = {
            "conc-01": Concession("conc-01", "North Tacos", Point(3, 12), ("tacos", "mexican", "quick"), True, 5, 1.1, "Fast moving location near Gate A."),
            "conc-02": Concession("conc-02", "Transit Bites", Point(7, 12), ("burgers", "fries", "quick"), True, 6, 1.2, "High throughput counter near Gate B."),
            "conc-03": Concession("conc-03", "Accessible Fresh Bowls", Point(13, 12), ("healthy", "salad", "gluten-free"), True, 4, 1.0, "Low queue option beside the accessible entry."),
            "conc-04": Concession("conc-04", "Club Kitchen", Point(16, 11), ("premium", "grill", "wine"), True, 8, 1.4, "Premium club menu with seated service."),
            "conc-05": Concession("conc-05", "Fan Zone Snacks", Point(4, 5), ("snacks", "soda", "ice-cream"), True, 5, 1.1, "Ideal for families in the fan zone."),
            "conc-06": Concession("conc-06", "South Street Pizza", Point(6, 4), ("pizza", "quick", "family"), True, 7, 1.2, "Popular during halftime."),
            "conc-07": Concession("conc-07", "West Wraps", Point(15, 5), ("wraps", "coffee", "quick"), True, 6, 1.1, "Convenient for west terrace supporters."),
            "conc-08": Concession("conc-08", "VIP Terrace Sushi", Point(19, 8), ("sushi", "premium", "vip"), True, 9, 1.5, "Exclusive menu with lounge seating."),
        }

        self.crews: dict[str, CleaningCrew] = {
            "crew-01": CleaningCrew("crew-01", "North", ("spill", "waste"), Point(2, 13)),
            "crew-02": CleaningCrew("crew-02", "Central", ("crowd_control", "routing"), Point(10, 10)),
            "crew-03": CleaningCrew("crew-03", "East", ("spill", "biohazard"), Point(16, 11)),
            "crew-04": CleaningCrew("crew-04", "South", ("waste", "floor_dry"), Point(5, 4)),
            "crew-05": CleaningCrew("crew-05", "West", ("crowd_control", "security_support"), Point(15, 6)),
        }

        self.alert_state = AlertState(
            level="green",
            active_incidents=[],
            public_message="Operations normal. Fan services are healthy.",
        )
        self.incident_counter = 0
        self.incident_history: list[IncidentRecord] = []

    def resolve_point(self, gate_id: str | None = None, location: dict | None = None) -> Point:
        if location:
            return Point(int(location["x"]), int(location["y"]))
        if gate_id:
            gate = self.gates.get(gate_id.lower())
            if gate:
                return gate.coordinate
        return Point(10, 8)

    def route(self, origin: Point, destination: Point, accessible: bool) -> dict:
        return {
            "origin": {"x": origin.x, "y": origin.y},
            "destination": {"x": destination.x, "y": destination.y},
            "distance_meters": round(distance_meters(origin, destination), 1),
            "estimated_minutes": max(1, round(distance_meters(origin, destination) / (60 if accessible else 78))),
            "steps": cardinal_steps(origin, destination, accessible),
            "accessible": accessible,
        }

    def preferred_sections(self, ticket_category: str, accessibility_required: bool) -> list[Section]:
        normalized = resolve_category_alias(ticket_category)
        candidates: list[Section] = []
        for section in self.sections.values():
            if accessibility_required and not section.accessible:
                continue
            if normalized in section.ticket_categories or "general" in section.ticket_categories or normalized == "accessible":
                candidates.append(section)
        candidates.sort(key=lambda section: (
            section.coordinate.x, section.coordinate.y))
        return candidates

    def nearest_gate(self, origin: Point, *, accessible_only: bool = False) -> Gate:
        gates = [gate for gate in self.gates.values() if (
            not accessible_only or gate.accessible)]
        return min(gates, key=lambda gate: distance_meters(origin, gate.coordinate))

    def nearest_section(self, origin: Point, ticket_category: str, accessibility_required: bool) -> Section:
        candidates = self.preferred_sections(
            ticket_category, accessibility_required)
        if not candidates:
            candidates = [section for section in self.sections.values(
            ) if not accessibility_required or section.accessible]
        return min(candidates, key=lambda section: distance_meters(origin, section.coordinate))

    def concession_wait_minutes(self, concession: Concession, origin: Point, incident_pressure: float = 0.0) -> int:
        distance_component = distance_meters(
            origin, concession.coordinate) / 25.0
        crowd_seed = stable_int(
            f"{concession.stall_id}:{now_utc().strftime('%Y%m%d%H%M')[:12]}")
        crowd_variation = (crowd_seed % 5) - 2
        alert_weight = {"green": 0, "yellow": 1, "amber": 3,
                        "red": 5, "black": 7}[self.alert_state.level]
        wait = concession.base_wait_minutes + distance_component + \
            (self.alert_state.active_incidents.__len__() * 1.5) + \
            alert_weight + incident_pressure + crowd_variation
        return int(clamp(wait, 1, 25))

    def recommend_concessions(self, origin: Point, ticket_category: str, question: str, limit: int = 3) -> list[dict]:
        normalized_question = question.lower()
        preferred_tags = []
        if any(keyword in normalized_question for keyword in ["pizza", "slice"]):
            preferred_tags.append("pizza")
        if any(keyword in normalized_question for keyword in ["healthy", "salad", "fresh"]):
            preferred_tags.append("healthy")
        if any(keyword in normalized_question for keyword in ["coffee", "drink"]):
            preferred_tags.append("coffee")
        if any(keyword in normalized_question for keyword in ["vip", "premium"]):
            preferred_tags.append("premium")

        scored: list[dict] = []
        for concession in self.concessions.values():
            wait_minutes = self.concession_wait_minutes(concession, origin)
            distance = distance_meters(origin, concession.coordinate)
            tag_boost = 0
            if preferred_tags and any(tag in concession.menu_tags for tag in preferred_tags):
                tag_boost -= 2
            if resolve_category_alias(ticket_category) == "accessible" and not concession.accessible:
                continue
            score = wait_minutes + (distance / 40.0) + tag_boost
            scored.append(
                {
                    "stall_id": concession.stall_id,
                    "name": concession.name,
                    "menu_tags": list(concession.menu_tags),
                    "distance_meters": round(distance, 1),
                    "wait_minutes": wait_minutes,
                    "accessible": concession.accessible,
                    "notes": concession.notes,
                    "score": round(score, 2),
                }
            )
        scored.sort(key=lambda item: (
            item["wait_minutes"], item["distance_meters"], item["score"]))
        return scored[:limit]

    def incident_pressure(self, location: Point) -> float:
        if not self.alert_state.active_incidents:
            return 0.0
        total_pressure = 0.0
        for incident in self.alert_state.active_incidents:
            incident_location = Point(
                incident["location"]["x"], incident["location"]["y"])
            total_pressure += max(0.0, 4.0 -
                                  (distance_meters(location, incident_location) / 100.0))
        return total_pressure

    def severity_rank(self, severity: str) -> int:
        return {"low": 1, "medium": 2, "high": 3, "critical": 4}.get(severity, 1)

    def alert_level_for_severity(self, severity: str) -> str:
        rank = self.severity_rank(severity)
        if rank >= 4:
            return "red"
        if rank == 3:
            return "amber"
        if rank == 2:
            return "yellow"
        return "green"

    def select_crews(self, incident_type: str, origin: Point, severity: str) -> list[CleaningCrew]:
        specialization_map = {
            "cleaning_spill": ("spill", "biohazard", "waste"),
            "crowd_bottleneck": ("crowd_control", "routing", "security_support"),
            "medical": ("security_support",),
            "security": ("security_support",),
            "general_ops": ("waste", "routing"),
        }
        required = specialization_map.get(incident_type, ("waste",))

        available_crews = sorted(
            self.crews.values(),
            key=lambda crew: (crew.status != "available",
                              distance_meters(origin, crew.current_location)),
        )
        selected: list[CleaningCrew] = []
        for crew in available_crews:
            if any(skill in crew.specialization for skill in required):
                selected.append(crew)
            if len(selected) == 2:
                break
        if not selected:
            selected = available_crews[:1]
        return selected

    def register_incident(self, report: str, location: Point, severity: str, incident_type: str) -> IncidentRecord:
        with self.lock:
            self.incident_counter += 1
            incident_id = f"INC-{self.incident_counter:04d}"
            record = IncidentRecord(
                incident_id=incident_id,
                incident_type=incident_type,
                report=report,
                location=location,
                severity=severity,  # type: ignore[arg-type]
                created_at=now_utc(),
            )
            self.incident_history.append(record)
            self.alert_state.active_incidents.append(
                {
                    "incident_id": incident_id,
                    "incident_type": incident_type,
                    "report": report,
                    "location": {"x": location.x, "y": location.y},
                    "severity": severity,
                }
            )
            return record

    def update_alert_state(self, severity: str, incident_type: str, report: str) -> AlertState:
        rank = self.severity_rank(severity)
        current_rank = self.severity_rank(self.alert_state.level if self.alert_state.level in {
                                          "green", "yellow", "amber", "red", "black"} else "green")
        candidate_rank = max(current_rank, min(rank + 1, 4))
        new_level = {1: "green", 2: "yellow", 3: "amber",
                     4: "red"}.get(candidate_rank, "red")
        if incident_type == "medical":
            new_level = "red" if rank >= 3 else "amber"
        self.alert_state.level = new_level  # type: ignore[assignment]
        self.alert_state.last_updated = now_utc()
        self.alert_state.public_message = f"Active {incident_type.replace('_', ' ')} incident under control. {report[:120]}"
        return self.alert_state

    def dispatch_crews(self, incident_record: IncidentRecord) -> list[dict]:
        selected = self.select_crews(
            incident_record.incident_type, incident_record.location, incident_record.severity)
        dispatches: list[dict] = []
        for crew in selected:
            crew.status = "en_route"
            crew.current_assignment = incident_record.incident_id
            crew.last_updated = now_utc()
            travel_distance = distance_meters(
                crew.current_location, incident_record.location)
            eta_minutes = max(1, round(travel_distance / 65.0))
            if incident_record.incident_type == "cleaning_spill":
                crew.status = "cleaning"
            dispatches.append(
                {
                    "crew_id": crew.crew_id,
                    "zone": crew.zone,
                    "status": crew.status,
                    "assignment": incident_record.incident_id,
                    "eta_minutes": eta_minutes,
                    "skills": list(crew.specialization),
                }
            )
        return dispatches


STADIUM_DB = StadiumDatabase()
