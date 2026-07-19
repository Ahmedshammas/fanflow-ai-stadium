from __future__ import annotations

import json
import os
import re
from typing import Any, Literal

from google import genai
from google.genai import types
from pydantic import BaseModel, ConfigDict, Field, field_validator

from stadium_data import STADIUM_DB, Point, incident_type_from_text, resolve_category_alias


class StadiumPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: int = Field(..., ge=0, le=50)
    y: int = Field(..., ge=0, le=50)


class FanChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticket_category: str = Field(default="general", examples=[
                                 "general", "premium", "vip", "accessible"])
    current_gate: str | None = Field(
        default=None, description="Current gate identifier such as gate-a.")
    current_location: StadiumPoint | None = Field(
        default=None, description="Current coordinate inside the stadium.")
    preferred_language: str = Field(
        default="en", description="Preferred response language code.")
    question: str = Field(..., min_length=3, max_length=500)

    @field_validator("ticket_category")
    @classmethod
    def normalize_ticket_category(cls, value: str) -> str:
        return resolve_category_alias(value)


class OpsIncidentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    volunteer_id: str = Field(..., min_length=2, max_length=64)
    location: StadiumPoint
    report: str = Field(..., min_length=5, max_length=700)
    severity_hint: str | None = Field(
        default=None, description="Optional volunteer severity hint.")


class RoutePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin: StadiumPoint
    destination: StadiumPoint
    distance_meters: float
    estimated_minutes: int
    steps: list[str]
    accessible: bool


class ConcessionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stall_id: str
    name: str
    menu_tags: list[str]
    distance_meters: float
    wait_minutes: int
    accessible: bool
    notes: str
    score: float


class FanChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Literal["route", "food", "accessibility", "general"]
    preferred_language: str
    assistant_message: str
    ticket_category: str
    current_gate: str | None
    route: RoutePayload | None = None
    section_recommendation: dict[str, Any] | None = None
    closest_concessions: list[ConcessionPayload] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    model_used: str


class CrewDispatchPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    crew_id: str
    zone: str
    status: str
    assignment: str
    eta_minutes: int
    skills: list[str]


class AlertStatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: Literal["green", "yellow", "amber", "red", "black"]
    active_incidents: list[dict[str, Any]]
    public_message: str
    last_updated: str


class OpsIncidentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_id: str
    incident_type: str
    severity: Literal["low", "medium", "high", "critical"]
    location: StadiumPoint
    dispatch_instructions: list[CrewDispatchPayload]
    alert_state: AlertStatePayload
    operational_actions: list[str]
    public_message: str
    model_used: str


class GeminiSupportMixin:
    model_name = "gemini-1.5-flash"

    def __init__(self, client: genai.Client | None = None) -> None:
        self.client = client

    @classmethod
    def create_client(cls) -> genai.Client | None:
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            return None
        return genai.Client(api_key=api_key)

    def _llm_message(self, payload: dict[str, Any], language: str, mode: str) -> str | None:
        if self.client is None:
            return None

        prompt = (
            f"You are a stadium operations assistant. Produce one concise message in the user's preferred language. "
            f"Return JSON only with keys: message, language, mode. Mode is {mode}. "
            f"Use this structured payload as ground truth: {json.dumps(payload, ensure_ascii=True)}. "
            f"Do not add markdown or extra keys."
        )
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    top_p=0.8,
                    max_output_tokens=280,
                    response_mime_type="application/json",
                ),
            )
            raw_text = getattr(response, "text", None)
            if not raw_text:
                return None
            parsed = json.loads(raw_text)
            message = str(parsed.get("message", "")).strip()
            if message:
                return message
        except Exception:
            return None
        return None

    def _fallback_message(self, payload: dict[str, Any], language: str, mode: str) -> str:
        if mode == "fan":
            route = payload.get("route")
            concessions = payload.get("closest_concessions", [])
            section = payload.get("section_recommendation")
            if route and section:
                return f"Head to {section.get('name')} and follow the route steps."
            if concessions:
                best = concessions[0]
                return f"Go to {best['name']} for the shortest queue at about {best['wait_minutes']} minutes."
            return "Your request is logged. Follow the recommended stadium route."
        return "Incident logged. Crews have been dispatched and the alert state has been updated."

    def _compose_message(self, payload: dict[str, Any], language: str, mode: str) -> str:
        polished = self._llm_message(payload, language, mode)
        if polished:
            return polished
        return self._fallback_message(payload, language, mode)


class FanAssistantAgent(GeminiSupportMixin):
    def chat(self, request: FanChatRequest) -> FanChatResponse:
        origin = STADIUM_DB.resolve_point(
            request.current_gate, request.current_location.model_dump() if request.current_location else None)
        accessibility_required = request.ticket_category == "accessible" or bool(
            re.search(r"wheelchair|accessible|ramp|mobility", request.question, re.I))
        question_lower = request.question.lower()
        intent = self._detect_intent(question_lower)

        notes: list[str] = []
        route_payload: dict[str, Any] | None = None
        section_recommendation: dict[str, Any] | None = None
        concessions: list[dict[str, Any]] = []

        if intent in {"route", "accessibility"}:
            section = STADIUM_DB.nearest_section(
                origin, request.ticket_category, accessibility_required)
            section_recommendation = {
                "section_id": section.section_id,
                "name": section.name,
                "accessible": section.accessible,
                "nearest_gate_id": section.nearest_gate_id,
                "notes": section.notes,
            }
            route_payload = STADIUM_DB.route(
                origin, section.coordinate, accessibility_required)
            notes.append(
                "Route is optimized from your current gate or location to the best matching section.")

        if intent in {"food", "general"} or any(keyword in question_lower for keyword in ["food", "eat", "drink", "coffee", "concession", "snack", "hungry"]):
            concessions = STADIUM_DB.recommend_concessions(
                origin, request.ticket_category, request.question, limit=3)
            notes.append(
                "Concession ranking blends live queue time with walking distance.")

        if accessibility_required and intent != "accessibility":
            notes.append(
                "Accessibility preference detected and enforced in route selection.")
            accessible_gate = STADIUM_DB.nearest_gate(
                origin, accessible_only=True)
            if request.current_gate and request.current_gate.lower() != accessible_gate.gate_id:
                notes.append(
                    f"Nearest accessible entrance is {accessible_gate.name}.")

        if not route_payload and request.current_gate:
            gate = STADIUM_DB.gates.get(request.current_gate.lower())
            if gate:
                section = STADIUM_DB.nearest_section(
                    origin, request.ticket_category, accessibility_required)
                route_payload = STADIUM_DB.route(
                    origin, section.coordinate, accessibility_required)
                section_recommendation = {
                    "section_id": section.section_id,
                    "name": section.name,
                    "accessible": section.accessible,
                    "nearest_gate_id": section.nearest_gate_id,
                    "notes": section.notes,
                }

        payload = {
            "intent": intent,
            "ticket_category": request.ticket_category,
            "current_gate": request.current_gate,
            "route": route_payload,
            "section_recommendation": section_recommendation,
            "closest_concessions": concessions,
            "notes": notes,
        }

        assistant_message = self._compose_message(
            payload, request.preferred_language, "fan")
        return FanChatResponse(
            intent=intent,
            preferred_language=request.preferred_language,
            assistant_message=assistant_message,
            ticket_category=request.ticket_category,
            current_gate=request.current_gate,
            route=RoutePayload(**route_payload) if route_payload else None,
            section_recommendation=section_recommendation,
            closest_concessions=[ConcessionPayload(
                **item) for item in concessions],
            notes=notes,
            model_used=self.model_name if self.client else "deterministic-fallback",
        )

    def _detect_intent(self, question: str) -> Literal["route", "food", "accessibility", "general"]:
        if any(keyword in question for keyword in ["wheelchair", "accessible", "ramp", "mobility", "accessibility"]):
            return "accessibility"
        if any(keyword in question for keyword in ["food", "eat", "drink", "coffee", "concession", "snack", "hungry", "restaurant"]):
            return "food"
        if any(keyword in question for keyword in ["where", "route", "path", "section", "gate", "walk", "how do i get"]):
            return "route"
        return "general"


class OpsCommanderAgent(GeminiSupportMixin):
    def process_incident(self, request: OpsIncidentRequest) -> OpsIncidentResponse:
        location = Point(request.location.x, request.location.y)
        incident_type, severity = incident_type_from_text(
            request.report, request.severity_hint)

        incident_record = STADIUM_DB.register_incident(
            request.report, location, severity, incident_type)
        STADIUM_DB.update_alert_state(severity, incident_type, request.report)
        dispatches = STADIUM_DB.dispatch_crews(incident_record)

        public_message = STADIUM_DB.alert_state.public_message
        operational_actions = self._operational_actions(
            incident_type, severity, dispatches)

        payload = {
            "incident_id": incident_record.incident_id,
            "incident_type": incident_type,
            "severity": severity,
            "location": {"x": location.x, "y": location.y},
            "dispatch_instructions": dispatches,
            "operational_actions": operational_actions,
            "public_message": public_message,
        }

        assistant_message = self._compose_message(payload, "en", "ops")
        return OpsIncidentResponse(
            incident_id=incident_record.incident_id,
            incident_type=incident_type,
            severity=severity,  # type: ignore[arg-type]
            location=StadiumPoint(x=location.x, y=location.y),
            dispatch_instructions=[CrewDispatchPayload(
                **dispatch) for dispatch in dispatches],
            alert_state=AlertStatePayload(
                level=STADIUM_DB.alert_state.level,
                active_incidents=STADIUM_DB.alert_state.active_incidents,
                public_message=STADIUM_DB.alert_state.public_message,
                last_updated=STADIUM_DB.alert_state.last_updated.isoformat(),
            ),
            operational_actions=operational_actions,
            public_message=assistant_message,
            model_used=self.model_name if self.client else "deterministic-fallback",
        )

    def _operational_actions(self, incident_type: str, severity: str, dispatches: list[dict[str, Any]]) -> list[str]:
        actions: list[str] = []
        if incident_type == "cleaning_spill":
            actions.append(
                "Close the affected aisle and deploy wet-floor signage immediately.")
            actions.append(
                "Assign cleaning crews with spill or biohazard skills to the exact coordinate.")
        elif incident_type == "crowd_bottleneck":
            actions.append(
                "Open a secondary lane and send crowd-control support to redirect fan flow.")
            actions.append(
                "Broadcast a low-friction routing update to nearby fans and volunteers.")
        elif incident_type == "medical":
            actions.append("Escalate to medical and security command at once.")
            actions.append(
                "Clear a protective perimeter before any cleanup activity begins.")
        else:
            actions.append(
                "Log the report, verify the site, and keep the area under observation.")

        if severity in {"high", "critical"}:
            actions.append(
                "Increase the alert level and notify the command desk immediately.")
        if dispatches:
            actions.append(
                f"Dispatch {len(dispatches)} crew unit(s) with ETA control and live status tracking.")
        return actions


def build_client() -> genai.Client | None:
    return GeminiSupportMixin.create_client()
