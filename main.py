from __future__ import annotations

import json
import os
from html import escape

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from agents import (
    FanAssistantAgent,
    FanChatRequest,
    FanChatResponse,
    OpsCommanderAgent,
    OpsIncidentRequest,
    OpsIncidentResponse,
    build_client,
)
from stadium_data import STADIUM_DB


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


def build_dashboard_context() -> dict[str, object]:
    active_gates = [gate for gate in STADIUM_DB.gates.values()
                    if gate.accessible]
    alert_state = STADIUM_DB.alert_state
    crew_status_counts: dict[str, int] = {
        "available": 0, "en_route": 0, "cleaning": 0, "paused": 0}
    for crew in STADIUM_DB.crews.values():
        crew_status_counts[crew.status] = crew_status_counts.get(
            crew.status, 0) + 1

    recent_incidents = list(
        reversed(STADIUM_DB.alert_state.active_incidents[-8:]))
    concession_waits = [
        {
            "stall_id": concession.stall_id,
            "name": concession.name,
            "wait_minutes": STADIUM_DB.concession_wait_minutes(concession, concession.coordinate),
            "notes": concession.notes,
        }
        for concession in STADIUM_DB.concessions.values()
    ]
    concession_waits.sort(key=lambda item: (
        item["wait_minutes"], item["name"]))

    return {
        "active_gates": active_gates,
        "total_gates": len(STADIUM_DB.gates),
        "total_sections": len(STADIUM_DB.sections),
        "total_concessions": len(STADIUM_DB.concessions),
        "alert_state": alert_state,
        "crew_status_counts": crew_status_counts,
        "recent_incidents": recent_incidents,
        "top_concessions": concession_waits[:4],
        "model": "gemini-1.5-flash" if app.state.fan_agent.client else "deterministic-fallback",
    }


def render_dashboard() -> str:
    context = build_dashboard_context()
    active_gates_json = json.dumps([
        {
            "gate_id": gate.gate_id,
            "name": gate.name,
            "x": gate.coordinate.x,
            "y": gate.coordinate.y,
            "accessible": gate.accessible,
            "ticket_categories": list(gate.ticket_categories),
            "notes": gate.notes,
        }
        for gate in context["active_gates"]
    ])
    top_concessions_json = json.dumps(context["top_concessions"])
    recent_incidents_json = json.dumps(context["recent_incidents"])

    alert_level = escape(context["alert_state"].level)
    alert_message = escape(context["alert_state"].public_message)
    alert_updated = escape(context["alert_state"].last_updated.isoformat())
    model_label = escape(str(context["model"]))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>FanFlow AI - Tournament Operations Command Center</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {{
            theme: {{
                extend: {{
                    colors: {{
                        ink: '#050816',
                        slateglass: '#111827',
                        neon: '#2dd4bf',
                        signal: '#f59e0b',
                        danger: '#ef4444',
                        calm: '#38bdf8'
                    }},
                    boxShadow: {{
                        glow: '0 0 0 1px rgba(45,212,191,0.2), 0 18px 60px rgba(0,0,0,0.45)'
                    }},
                    animation: {{
                        floaty: 'floaty 10s ease-in-out infinite'
                    }},
                    keyframes: {{
                        floaty: {{
                            '0%, 100%': {{ transform: 'translateY(0px)' }},
                            '50%': {{ transform: 'translateY(-10px)' }}
                        }}
                    }}
                }}
            }}
        }}
    </script>
    <style>
        body {{
            background:
                radial-gradient(circle at top left, rgba(45, 212, 191, 0.18), transparent 28%),
                radial-gradient(circle at top right, rgba(56, 189, 248, 0.14), transparent 22%),
                linear-gradient(180deg, #020617 0%, #040b1c 45%, #08111e 100%);
            color: #e5eef7;
        }}
        .grid-overlay {{
            background-image:
                linear-gradient(rgba(148, 163, 184, 0.06) 1px, transparent 1px),
                linear-gradient(90deg, rgba(148, 163, 184, 0.06) 1px, transparent 1px);
            background-size: 34px 34px;
        }}
    </style>
</head>
<body class="min-h-screen text-slate-100">
    <div class="fixed inset-0 grid-overlay opacity-40 pointer-events-none"></div>
    <main class="relative mx-auto max-w-7xl px-4 py-8 lg:px-8">
        <section class="mb-8 overflow-hidden rounded-3xl border border-white/10 bg-white/5 shadow-glow backdrop-blur-xl">
            <div class="grid gap-8 p-6 lg:grid-cols-[1.4fr_1fr] lg:p-8">
                <div>
                    <div class="inline-flex items-center gap-2 rounded-full border border-neon/30 bg-neon/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.3em] text-neon">
                        FanFlow AI Command Center
                    </div>
                    <h1 class="mt-4 text-4xl font-black tracking-tight text-white md:text-6xl">FanFlow AI - Tournament Operations Command Center</h1>
                    <p class="mt-4 max-w-3xl text-base leading-7 text-slate-300 md:text-lg">
                        Live tournament visibility for gate flow, concession demand, and incident response. This dashboard is wired directly to the same stadium intelligence that powers the FastAPI endpoints.
                    </p>
                    <div class="mt-6 flex flex-wrap gap-3 text-sm text-slate-300">
                        <span class="rounded-full border border-white/10 bg-slateglass px-4 py-2">Model: {model_label}</span>
                        <span class="rounded-full border border-white/10 bg-slateglass px-4 py-2">Alert level: <span class="font-semibold text-white">{alert_level}</span></span>
                        <span class="rounded-full border border-white/10 bg-slateglass px-4 py-2">Updated: {alert_updated}</span>
                    </div>
                </div>
                <div class="relative rounded-3xl border border-white/10 bg-slate-950/70 p-5 shadow-2xl animate-floaty">
                    <div class="mb-4 flex items-center justify-between">
                        <div>
                            <p class="text-xs uppercase tracking-[0.35em] text-calm/80">Stadium pulse</p>
                            <p class="mt-1 text-2xl font-bold text-white">Operations snapshot</p>
                        </div>
                        <div class="rounded-2xl border border-white/10 bg-white/5 px-3 py-2 text-right">
                            <p class="text-[11px] uppercase tracking-[0.3em] text-slate-400">Status</p>
                            <p class="text-sm font-semibold text-white">{alert_level}</p>
                        </div>
                    </div>
                    <div class="grid grid-cols-2 gap-3">
                        <div class="rounded-2xl border border-white/10 bg-white/5 p-4">
                            <p class="text-xs uppercase tracking-[0.25em] text-slate-400">Active gates</p>
                            <p class="mt-2 text-3xl font-black text-white">{context['total_gates']}</p>
                        </div>
                        <div class="rounded-2xl border border-white/10 bg-white/5 p-4">
                            <p class="text-xs uppercase tracking-[0.25em] text-slate-400">Concessions</p>
                            <p class="mt-2 text-3xl font-black text-white">{context['total_concessions']}</p>
                        </div>
                        <div class="rounded-2xl border border-white/10 bg-white/5 p-4">
                            <p class="text-xs uppercase tracking-[0.25em] text-slate-400">Sections</p>
                            <p class="mt-2 text-3xl font-black text-white">{context['total_sections']}</p>
                        </div>
                        <div class="rounded-2xl border border-white/10 bg-white/5 p-4">
                            <p class="text-xs uppercase tracking-[0.25em] text-slate-400">Incidents</p>
                            <p class="mt-2 text-3xl font-black text-white">{len(context['recent_incidents'])}</p>
                        </div>
                    </div>
                    <p class="mt-4 text-sm leading-6 text-slate-300">{alert_message}</p>
                </div>
            </div>
        </section>

        <section class="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
            <div class="space-y-6">
                <div class="rounded-3xl border border-white/10 bg-white/5 p-6 shadow-glow backdrop-blur-xl">
                    <div class="flex items-center justify-between">
                        <div>
                            <p class="text-xs uppercase tracking-[0.35em] text-neon/80">Live stadium stats</p>
                            <h2 class="mt-2 text-2xl font-bold text-white">Gates, concessions, and crew state</h2>
                        </div>
                        <div class="text-right text-sm text-slate-300">
                            <p>Accessible gates: <span class="font-semibold text-white">{len(context['active_gates'])}</span></p>
                            <p>Available crews: <span class="font-semibold text-white">{context['crew_status_counts'].get('available', 0)}</span></p>
                        </div>
                    </div>
                    <div class="mt-6 grid gap-4 md:grid-cols-2">
                        <div class="rounded-2xl border border-white/10 bg-slate-950/70 p-4">
                            <p class="text-sm font-semibold text-white">Gate map</p>
                            <div class="mt-3 space-y-3">
                                {''.join(f'<div class="flex items-center justify-between rounded-xl border border-white/5 bg-white/5 px-3 py-2"><span class="font-medium text-slate-100">{escape(gate.name)}</span><span class="text-xs text-neon">{"Accessible" if gate.accessible else "Standard"}</span></div>' for gate in context['active_gates'])}
                            </div>
                        </div>
                        <div class="rounded-2xl border border-white/10 bg-slate-950/70 p-4">
                            <p class="text-sm font-semibold text-white">Fastest concessions</p>
                            <div class="mt-3 space-y-3">
                                {''.join(f'<div class="flex items-center justify-between rounded-xl border border-white/5 bg-white/5 px-3 py-2"><div><p class="font-medium text-slate-100">{escape(item["name"])}</p><p class="text-xs text-slate-400">{escape(item["notes"])}</p></div><span class="rounded-full bg-calm/10 px-3 py-1 text-sm font-semibold text-calm">{item["wait_minutes"]}m</span></div>' for item in context['top_concessions'])}
                            </div>
                        </div>
                    </div>
                    <div class="mt-4 grid gap-3 sm:grid-cols-4">
                        {''.join(f'<div class="rounded-2xl border border-white/10 bg-white/5 p-4"><p class="text-xs uppercase tracking-[0.25em] text-slate-400">{escape(status.replace("_", " "))}</p><p class="mt-2 text-2xl font-black text-white">{count}</p></div>' for status, count in context['crew_status_counts'].items())}
                    </div>
                </div>

                <div class="rounded-3xl border border-white/10 bg-white/5 p-6 shadow-glow backdrop-blur-xl">
                    <div class="flex items-center justify-between">
                        <div>
                            <p class="text-xs uppercase tracking-[0.35em] text-calm/80">Fan Assistant</p>
                            <h2 class="mt-2 text-2xl font-bold text-white">Interactive chat tester</h2>
                        </div>
                        <span class="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs uppercase tracking-[0.3em] text-slate-300">/api/fan/chat</span>
                    </div>

                    <div class="mt-6 grid gap-4 md:grid-cols-2">
                        <label class="block">
                            <span class="text-sm text-slate-300">Ticket category</span>
                            <select id="fan-ticket" class="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950/90 px-4 py-3 text-white outline-none ring-0 focus:border-neon/60">
                                <option>general</option>
                                <option>premium</option>
                                <option>vip</option>
                                <option>accessible</option>
                                <option>family</option>
                            </select>
                        </label>
                        <label class="block">
                            <span class="text-sm text-slate-300">Preferred language</span>
                            <input id="fan-language" value="en" class="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950/90 px-4 py-3 text-white outline-none ring-0 focus:border-neon/60" />
                        </label>
                        <label class="block">
                            <span class="text-sm text-slate-300">Current gate</span>
                            <input id="fan-gate" value="gate-b" class="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950/90 px-4 py-3 text-white outline-none ring-0 focus:border-neon/60" />
                        </label>
                        <label class="block">
                            <span class="text-sm text-slate-300">Current location (x,y)</span>
                            <input id="fan-location" value="8,13" class="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950/90 px-4 py-3 text-white outline-none ring-0 focus:border-neon/60" />
                        </label>
                    </div>

                    <label class="mt-4 block">
                        <span class="text-sm text-slate-300">Question</span>
                        <textarea id="fan-question" rows="4" class="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950/90 px-4 py-3 text-white outline-none ring-0 focus:border-neon/60">Where is the fastest accessible route to food and my section?</textarea>
                    </label>

                    <div class="mt-4 flex flex-wrap gap-3">
                        <button id="fan-send" class="rounded-2xl bg-neon px-5 py-3 font-semibold text-slate-950 transition hover:brightness-110">Send to Fan Assistant</button>
                        <button id="fan-example" class="rounded-2xl border border-white/10 bg-white/5 px-5 py-3 font-semibold text-white transition hover:bg-white/10">Load route example</button>
                    </div>

                    <pre id="fan-response" class="mt-5 min-h-40 overflow-auto rounded-3xl border border-white/10 bg-slate-950/95 p-4 text-sm leading-6 text-slate-200">Fan Assistant responses will appear here.</pre>
                </div>
            </div>

            <div class="space-y-6">
                <div class="rounded-3xl border border-white/10 bg-white/5 p-6 shadow-glow backdrop-blur-xl">
                    <div class="flex items-center justify-between">
                        <div>
                            <p class="text-xs uppercase tracking-[0.35em] text-signal/80">Operations intake</p>
                            <h2 class="mt-2 text-2xl font-bold text-white">Volunteer incident log</h2>
                        </div>
                        <span class="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs uppercase tracking-[0.3em] text-slate-300">/api/ops/incident</span>
                    </div>

                    <div class="mt-6 space-y-4">
                        <label class="block">
                            <span class="text-sm text-slate-300">Volunteer ID</span>
                            <input id="ops-volunteer" value="vol-17" class="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950/90 px-4 py-3 text-white outline-none ring-0 focus:border-signal/60" />
                        </label>
                        <label class="block">
                            <span class="text-sm text-slate-300">Location (x,y)</span>
                            <input id="ops-location" value="4,5" class="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950/90 px-4 py-3 text-white outline-none ring-0 focus:border-signal/60" />
                        </label>
                        <label class="block">
                            <span class="text-sm text-slate-300">Severity hint</span>
                            <select id="ops-severity" class="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950/90 px-4 py-3 text-white outline-none ring-0 focus:border-signal/60">
                                <option value="">auto</option>
                                <option>low</option>
                                <option>medium</option>
                                <option>high</option>
                                <option>critical</option>
                            </select>
                        </label>
                        <label class="block">
                            <span class="text-sm text-slate-300">Incident report</span>
                            <textarea id="ops-report" rows="5" class="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950/90 px-4 py-3 text-white outline-none ring-0 focus:border-signal/60">Major spill near the south concourse creating a slip hazard and crowd slowdown.</textarea>
                        </label>
                    </div>

                    <div class="mt-4 flex flex-wrap gap-3">
                        <button id="ops-send" class="rounded-2xl bg-signal px-5 py-3 font-semibold text-slate-950 transition hover:brightness-110">Submit Incident</button>
                        <button id="ops-example" class="rounded-2xl border border-white/10 bg-white/5 px-5 py-3 font-semibold text-white transition hover:bg-white/10">Load crowd bottleneck example</button>
                    </div>

                    <pre id="ops-response" class="mt-5 min-h-40 overflow-auto rounded-3xl border border-white/10 bg-slate-950/95 p-4 text-sm leading-6 text-slate-200">Incident responses will appear here.</pre>
                </div>

                <div class="rounded-3xl border border-white/10 bg-white/5 p-6 shadow-glow backdrop-blur-xl">
                    <div class="flex items-center justify-between">
                        <div>
                            <p class="text-xs uppercase tracking-[0.35em] text-danger/80">Incident monitor</p>
                            <h2 class="mt-2 text-2xl font-bold text-white">Incoming volunteer activity</h2>
                        </div>
                        <span class="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs uppercase tracking-[0.3em] text-slate-300">Live log</span>
                    </div>
                    <div id="incident-log" class="mt-5 space-y-3">
                        {''.join(f'<div class="rounded-2xl border border-white/10 bg-slate-950/80 p-4"><div class="flex items-center justify-between"><p class="font-semibold text-white">{escape(item.get("incident_type", "incident"))}</p><span class="text-xs text-slate-400">{escape(item.get("severity", "low"))}</span></div><p class="mt-2 text-sm text-slate-300">{escape(item.get("report", ""))}</p></div>' for item in recent_incidents_json and json.loads(recent_incidents_json)) if json.loads(recent_incidents_json) else '<div class="rounded-2xl border border-dashed border-white/10 bg-slate-950/60 p-4 text-sm text-slate-400">No incidents have been logged yet. Submit one from the operations panel.</div>'}
                    </div>
                </div>
            </div>
        </section>
    </main>

    <script>
        const activeGates = {active_gates_json};
        const recentIncidents = {recent_incidents_json};
        const topConcessions = {top_concessions_json};
        const incidentLog = document.getElementById('incident-log');
        const fanResponse = document.getElementById('fan-response');
        const opsResponse = document.getElementById('ops-response');

        function escapeHtml(text) {{
            return String(text)
                .replaceAll('&', '&amp;')
                .replaceAll('<', '&lt;')
                .replaceAll('>', '&gt;')
                .replaceAll('"', '&quot;')
                .replaceAll("'", '&#039;');
        }}

        function renderIncident(item) {{
            const card = document.createElement('div');
            card.className = 'rounded-2xl border border-white/10 bg-slate-950/80 p-4';
            card.innerHTML = `
                <div class="flex items-center justify-between gap-4">
                    <p class="font-semibold text-white">${{escapeHtml(item.incident_type || 'incident')}}</p>
                    <span class="text-xs text-slate-400">${{escapeHtml(item.severity || 'low')}}</span>
                </div>
                <p class="mt-2 text-sm text-slate-300">${{escapeHtml(item.report || '')}}</p>
                <div class="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-400 md:grid-cols-4">
                    <span>Dispatch: ${{item.dispatch_instructions ? item.dispatch_instructions.length : 0}}</span>
                    <span>Alert: ${{escapeHtml(item.alert_state ? item.alert_state.level : 'n/a')}}</span>
                    <span>ETA: ${{item.dispatch_instructions && item.dispatch_instructions[0] ? item.dispatch_instructions[0].eta_minutes + 'm' : 'n/a'}}</span>
                    <span>Model: ${{escapeHtml(item.model_used || 'deterministic')}}</span>
                </div>`;
            incidentLog.prepend(card);
        }}

        async function postJson(url, payload) {{
            const response = await fetch(url, {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify(payload)
            }});
            const data = await response.json();
            if (!response.ok) {{
                throw new Error(data.detail || 'Request failed');
            }}
            return data;
        }}

        function parsePoint(value) {{
            const [x, y] = String(value).split(',').map(part => Number.parseInt(part.trim(), 10));
            return {{ x: Number.isFinite(x) ? x : 10, y: Number.isFinite(y) ? y : 8 }};
        }}

        document.getElementById('fan-example').addEventListener('click', () => {{
            document.getElementById('fan-ticket').value = 'accessible';
            document.getElementById('fan-gate').value = 'gate-b';
            document.getElementById('fan-language').value = 'en';
            document.getElementById('fan-location').value = '8,13';
            document.getElementById('fan-question').value = 'Where is the fastest accessible route to the section and the shortest concession queue?';
        }});

        document.getElementById('ops-example').addEventListener('click', () => {{
            document.getElementById('ops-volunteer').value = 'vol-24';
            document.getElementById('ops-location').value = '9,7';
            document.getElementById('ops-severity').value = 'high';
            document.getElementById('ops-report').value = 'Crowd bottleneck near west access stairs. Volunteers need direction support and queue management.';
        }});

        document.getElementById('fan-send').addEventListener('click', async () => {{
            const payload = {{
                ticket_category: document.getElementById('fan-ticket').value,
                current_gate: document.getElementById('fan-gate').value,
                current_location: parsePoint(document.getElementById('fan-location').value),
                preferred_language: document.getElementById('fan-language').value,
                question: document.getElementById('fan-question').value
            }};
            fanResponse.textContent = 'Sending fan request...';
            try {{
                const data = await postJson('/api/fan/chat', payload);
                fanResponse.textContent = JSON.stringify(data, null, 2);
            }} catch (error) {{
                fanResponse.textContent = `Request failed: ${{error.message}}`;
            }}
        }});

        document.getElementById('ops-send').addEventListener('click', async () => {{
            const payload = {{
                volunteer_id: document.getElementById('ops-volunteer').value,
                location: parsePoint(document.getElementById('ops-location').value),
                severity_hint: document.getElementById('ops-severity').value || null,
                report: document.getElementById('ops-report').value
            }};
            opsResponse.textContent = 'Submitting incident...';
            try {{
                const data = await postJson('/api/ops/incident', payload);
                opsResponse.textContent = JSON.stringify(data, null, 2);
                renderIncident(data);
            }} catch (error) {{
                opsResponse.textContent = `Request failed: ${{error.message}}`;
            }}
        }});

        if (recentIncidents.length) {{
            recentIncidents.slice().reverse().forEach((incident) => renderIncident({{
                incident_type: incident.incident_type,
                report: incident.report,
                severity: incident.severity,
                dispatch_instructions: [],
                alert_state: {{ level: '{alert_level}' }},
                model_used: '{model_label}'
            }}));
        }}
    </script>
</body>
</html>"""


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {
        "status": "ok",
        "model": "gemini-1.5-flash" if app.state.fan_agent.client else "deterministic-fallback",
    }


@app.get("/", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    return HTMLResponse(render_dashboard())


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
