from __future__ import annotations

from fastapi.testclient import TestClient

from main import app


def assert_healthz(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200, response.text

    body = response.json()
    assert isinstance(body, dict)
    assert body["status"] == "ok"
    assert isinstance(body["model"], str)
    assert body["model"]


def assert_fan_response_structure(body: dict, expected_language: str) -> None:
    assert body["intent"] in {"route", "food", "accessibility", "general"}
    assert body["preferred_language"] == expected_language
    assert isinstance(body["assistant_message"], str)
    assert body["assistant_message"]
    assert isinstance(body["ticket_category"], str)
    assert isinstance(body["current_gate"], (str, type(None)))
    assert isinstance(body["model_used"], str)
    assert body["model_used"]
    assert isinstance(body["notes"], list)
    assert all(isinstance(item, str) for item in body["notes"])
    assert isinstance(body["closest_concessions"], list)

    if body["route"] is not None:
        route = body["route"]
        assert isinstance(route["origin"], dict)
        assert isinstance(route["destination"], dict)
        assert isinstance(route["distance_meters"], (int, float))
        assert isinstance(route["estimated_minutes"], int)
        assert isinstance(route["steps"], list)
        assert isinstance(route["accessible"], bool)

    for concession in body["closest_concessions"]:
        assert isinstance(concession["stall_id"], str)
        assert isinstance(concession["name"], str)
        assert isinstance(concession["menu_tags"], list)
        assert isinstance(concession["distance_meters"], (int, float))
        assert isinstance(concession["wait_minutes"], int)
        assert isinstance(concession["accessible"], bool)
        assert isinstance(concession["notes"], str)
        assert isinstance(concession["score"], (int, float))


def assert_standard_fan_chat(client: TestClient) -> None:
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
    assert_fan_response_structure(body, "en")
    assert body["route"] is not None
    assert body["route"]["accessible"] is True
    assert body["section_recommendation"] is not None
    assert isinstance(body["section_recommendation"], dict)
    assert body["closest_concessions"], "Expected at least one concession recommendation"
    assert body["closest_concessions"][0]["wait_minutes"] <= 25


def assert_multilingual_fan_chat(client: TestClient) -> None:
    payload = {
        "ticket_category": "premium",
        "current_gate": "gate-g",
        "preferred_language": "es",
        "question": "¿Cuál es la mejor ruta y la comida más cercana?",
    }
    response = client.post("/api/fan/chat", json=payload)
    assert response.status_code == 200, response.text

    body = response.json()
    assert_fan_response_structure(body, "es")
    assert body["assistant_message"].strip()
    assert isinstance(body["assistant_message"], str)
    assert body["route"] is not None or body["closest_concessions"]


def assert_edge_case_fan_chat(client: TestClient) -> None:
    payload = {
        "ticket_category": "general",
        "current_location": {"x": 50, "y": 0},
        "preferred_language": "en",
        "question": "How do I get to the nearest section from here?",
    }
    response = client.post("/api/fan/chat", json=payload)
    assert response.status_code == 200, response.text

    body = response.json()
    assert_fan_response_structure(body, "en")
    assert body["current_gate"] is None
    assert body["route"] is not None
    assert isinstance(body["route"]["origin"]["x"], int)
    assert isinstance(body["route"]["origin"]["y"], int)
    assert isinstance(body["route"]["destination"]["x"], int)
    assert isinstance(body["route"]["destination"]["y"], int)
    assert body["route"]["destination"]["x"] >= 0
    assert body["route"]["destination"]["y"] >= 0


def assert_ops_endpoint(client: TestClient) -> None:
    payload = {
        "volunteer_id": "vol-17",
        "location": {"x": 4, "y": 5},
        "report": "Major spill near the south concourse creating a slip hazard and crowd slowdown.",
        "severity_hint": "high",
    }
    response = client.post("/api/ops/incident", json=payload)
    assert response.status_code == 200, response.text

    body = response.json()
    assert isinstance(body, dict)
    assert body["incident_id"].startswith("INC-")
    assert body["incident_type"] in {
        "cleaning_spill",
        "crowd_bottleneck",
        "medical",
        "security",
        "general_ops",
    }
    assert body["severity"] in {"low", "medium", "high", "critical"}
    assert isinstance(body["location"], dict)
    assert isinstance(body["location"]["x"], int)
    assert isinstance(body["location"]["y"], int)

    assert isinstance(body["dispatch_instructions"], list)
    assert body["dispatch_instructions"], "Expected crew dispatch instructions"
    for dispatch in body["dispatch_instructions"]:
        assert isinstance(dispatch["crew_id"], str)
        assert isinstance(dispatch["zone"], str)
        assert isinstance(dispatch["status"], str)
        assert isinstance(dispatch["assignment"], str)
        assert isinstance(dispatch["eta_minutes"], int)
        assert isinstance(dispatch["skills"], list)

    assert isinstance(body["alert_state"], dict)
    assert body["alert_state"]["level"] in {
        "green", "yellow", "amber", "red", "black"}
    assert isinstance(body["alert_state"]["active_incidents"], list)
    assert isinstance(body["alert_state"]["public_message"], str)
    assert isinstance(body["alert_state"]["last_updated"], str)
    assert any(
        incident["incident_id"] == body["incident_id"]
        for incident in body["alert_state"]["active_incidents"]
    )

    assert isinstance(body["operational_actions"], list)
    assert body["operational_actions"], "Expected operational actions"
    assert all(isinstance(action, str)
               for action in body["operational_actions"])
    assert isinstance(body["public_message"], str)
    assert body["public_message"]
    assert isinstance(body["model_used"], str)
    assert body["model_used"]


def main() -> None:
    client = TestClient(app)
    assert_healthz(client)
    assert_standard_fan_chat(client)
    assert_multilingual_fan_chat(client)
    assert_edge_case_fan_chat(client)
    assert_ops_endpoint(client)
    print("Validation passed: health, fan chat, multilingual handling, edge cases, and ops incident endpoints are working.")


if __name__ == "__main__":
    main()
