from __future__ import annotations

import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException

from agents import (
    FanAssistantAgent,
    FanChatRequest,
    FanChatResponse,
    OpsCommanderAgent,
    OpsIncidentRequest,
    OpsIncidentResponse,
    build_client,
)


load_dotenv()

app = FastAPI(
    title="Smart Stadiums & Tournament Operations",
    version="1.0.0",
    description="Production-ready stadium fan services and incident operations for FIFA World Cup 2026.",
)


def create_agents() -> tuple[FanAssistantAgent, OpsCommanderAgent]:
    client = build_client()
    return FanAssistantAgent(client=client), OpsCommanderAgent(client=client)


fan_agent, ops_agent = create_agents()
app.state.fan_agent = fan_agent
app.state.ops_agent = ops_agent


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {
        "status": "ok",
        "model": "gemini-1.5-flash" if app.state.fan_agent.client else "deterministic-fallback",
    }


@app.post("/api/fan/chat", response_model=FanChatResponse)
def fan_chat(request: FanChatRequest) -> FanChatResponse:
    try:
        return app.state.fan_agent.chat(request)
    except Exception as exc:  # pragma: no cover - safety boundary
        raise HTTPException(
            status_code=500, detail=f"Fan assistant failed: {exc}") from exc


@app.post("/api/ops/incident", response_model=OpsIncidentResponse)
def ops_incident(request: OpsIncidentRequest) -> OpsIncidentResponse:
    try:
        return app.state.ops_agent.process_incident(request)
    except Exception as exc:  # pragma: no cover - safety boundary
        raise HTTPException(
            status_code=500, detail=f"Operations commander failed: {exc}") from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=int(
        os.getenv("PORT", "8000")), reload=False)
