from __future__ import annotations

from fastapi.testclient import TestClient

from main import app


def validate_fan_endpoint(client: TestClient) -> None:
    payload = {
        "ticket_category": "accessible",
        "current_gate": "gate-b",
        "current_location": {"x": 8, "y": 13},
        "preferred_language": "en",
        "question": "Where is the fastest accessible route to food and my section?",
    }
    response = client.post("/api/fan/chat", json=payload)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["intent"] in {"route", "food", "accessibility", "general"}
    assert body["model_used"]
    assert body["assistant_message"]
    assert body["route"] is not None
    assert body["route"]["accessible"] is True
    assert body["section_recommendation"] is not None
    assert body["closest_concessions"], "Expected at least one concession recommendation"
    assert body["closest_concessions"][0]["wait_minutes"] <= 25


def validate_ops_endpoint(client: TestClient) -> None:
    payload = {
        "volunteer_id": "vol-17",
        "location": {"x": 4, "y": 5},
        "report": "Major spill near the south concourse creating a slip hazard and crowd slowdown.",
        "severity_hint": "high",
    }
    response = client.post("/api/ops/incident", json=payload)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["incident_id"].startswith("INC-")
    assert body["incident_type"] in {
        "cleaning_spill", "crowd_bottleneck", "medical", "security", "general_ops"}
    assert body["dispatch_instructions"], "Expected crew dispatch instructions"
    assert body["alert_state"]["level"] in {
        "green", "yellow", "amber", "red", "black"}
    assert body["operational_actions"], "Expected operational actions"
    assert body["public_message"]


def main() -> None:
    client = TestClient(app)
    validate_fan_endpoint(client)
    validate_ops_endpoint(client)
    print("Validation passed: fan chat and ops incident endpoints are working.")


if __name__ == "__main__":
    main()
