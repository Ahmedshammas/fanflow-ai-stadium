from __future__ import annotations

import json
import os
from html import escape
from functools import lru_cache

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


@lru_cache(maxsize=1)
def build_static_dashboard_assets() -> dict[str, object]:
    accessible_gates = [
        {
            "gate_id": gate.gate_id,
            "name": gate.name,
            "x": gate.coordinate.x,
            "y": gate.coordinate.y,
            "accessible": gate.accessible,
            "ticket_categories": list(gate.ticket_categories),
            "notes": gate.notes,
        }
        for gate in STADIUM_DB.gates.values()
        if gate.accessible
    ]

    concessions = [
        {
            "stall_id": concession.stall_id,
            "name": concession.name,
            "coordinate": {"x": concession.coordinate.x, "y": concession.coordinate.y},
            "menu_tags": list(concession.menu_tags),
            "accessible": concession.accessible,
            "notes": concession.notes,
        }
        for concession in STADIUM_DB.concessions.values()
    ]

    return {
        "accessible_gates": accessible_gates,
        "total_gates": len(STADIUM_DB.gates),
        "total_sections": len(STADIUM_DB.sections),
        "total_concessions": len(STADIUM_DB.concessions),
        "concessions": concessions,
        "model": "gemini-1.5-flash" if app.state.fan_agent.client else "deterministic-fallback",
    }


def build_dashboard_context() -> dict[str, object]:
    static_assets = build_static_dashboard_assets()
    alert_state = STADIUM_DB.alert_state
    crew_status_counts: dict[str, int] = {
        "available": 0, "en_route": 0, "cleaning": 0, "paused": 0}
    for crew in STADIUM_DB.crews.values():
        crew_status_counts[crew.status] = crew_status_counts.get(
            crew.status, 0) + 1

    recent_incidents = list(reversed(alert_state.active_incidents[-8:]))
    concession_waits = [
        {
            "stall_id": concession["stall_id"],
            "name": concession["name"],
            "wait_minutes": STADIUM_DB.concession_wait_minutes(
                STADIUM_DB.concessions[concession["stall_id"]],
                STADIUM_DB.concessions[concession["stall_id"]].coordinate,
            ),
            "notes": concession["notes"],
        }
        for concession in static_assets["concessions"]
    ]
    concession_waits.sort(key=lambda item: (
        item["wait_minutes"], item["name"]))

    return {
        "active_gates": static_assets["accessible_gates"],
        "total_gates": static_assets["total_gates"],
        "total_sections": static_assets["total_sections"],
        "total_concessions": static_assets["total_concessions"],
        "alert_state": alert_state,
        "crew_status_counts": crew_status_counts,
        "recent_incidents": recent_incidents,
        "top_concessions": concession_waits[:4],
        "model": static_assets["model"],
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
    recent_incident_cards = "".join(
        f'<article class="rounded-2xl border border-slate-200/20 bg-slate-900/90 p-4">'
        f'<div class="flex items-center justify-between gap-4">'
        f'<h3 class="font-semibold text-white">{escape(item.get("incident_type", "incident"))}</h3>'
        f'<span class="text-xs text-slate-300">{escape(item.get("severity", "low"))}</span>'
        f'</div>'
        f'<p class="mt-2 text-sm text-slate-200">{escape(item.get("report", ""))}</p>'
        f'</article>'
        for item in recent_incidents_json and json.loads(recent_incidents_json)
    ) if json.loads(recent_incidents_json) else (
        '<article class="rounded-2xl border border-dashed border-slate-200/20 bg-slate-900/80 p-4 text-sm text-slate-200">'
        'No incidents have been logged yet. Submit one from the operations panel.'
        '</article>'
    )

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
                        ink: '#020617',
                        panel: '#0f172a',
                        panelStrong: '#111827',
                        neon: '#34d399',
                        signal: '#fbbf24',
                        danger: '#f87171',
                        calm: '#7dd3fc'
                    }},
                    boxShadow: {{
                        glow: '0 0 0 1px rgba(255,255,255,0.10), 0 18px 60px rgba(0,0,0,0.55)'
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
            color: #f8fafc;
            background:
                radial-gradient(circle at top left, rgba(52, 211, 153, 0.15), transparent 28%),
                radial-gradient(circle at top right, rgba(125, 211, 252, 0.12), transparent 22%),
                linear-gradient(180deg, #020617 0%, #030712 45%, #0f172a 100%);
        }}
        .grid-overlay {{
            background-image:
                linear-gradient(rgba(226, 232, 240, 0.08) 1px, transparent 1px),
                linear-gradient(90deg, rgba(226, 232, 240, 0.08) 1px, transparent 1px);
            background-size: 34px 34px;
        }}
    </style>
</head>
<body class="min-h-screen bg-ink text-slate-50">
    <div class="fixed inset-0 grid-overlay opacity-40 pointer-events-none"></div>
    <header class="relative mx-auto max-w-7xl px-4 pt-6 lg:px-8" role="banner">
        <div class="rounded-3xl border border-slate-200/20 bg-slate-950/90 px-5 py-4 shadow-glow backdrop-blur-xl">
            <p class="text-sm font-semibold text-emerald-300">Accessible live operations dashboard</p>
            <p class="mt-1 text-sm text-slate-300">FastAPI routes remain unchanged: /api/fan/chat and /api/ops/incident.</p>
        </div>
    </header>
    <main id="main-content" class="relative mx-auto max-w-7xl px-4 py-8 lg:px-8" aria-label="FanFlow AI command center content">
        <section class="mb-8 overflow-hidden rounded-3xl border border-slate-200/20 bg-slate-950/90 shadow-glow backdrop-blur-xl" aria-labelledby="overview-title">
            <div class="grid gap-8 p-6 lg:grid-cols-[1.4fr_1fr] lg:p-8">
                <div>
                    <div class="inline-flex items-center gap-2 rounded-full border border-emerald-300/30 bg-emerald-400/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.3em] text-emerald-200">
                        FanFlow AI Command Center
                    </div>
                    <h1 id="overview-title" class="mt-4 text-4xl font-black tracking-tight text-white md:text-6xl">FanFlow AI - Tournament Operations Command Center</h1>
                    <p class="mt-4 max-w-3xl text-base leading-7 text-slate-200 md:text-lg">
                        Live tournament visibility for gate flow, concession demand, and incident response. This dashboard is wired directly to the same stadium intelligence that powers the FastAPI endpoints.
                    </p>
                    <div class="mt-6 flex flex-wrap gap-3 text-sm text-slate-200">
                        <span class="rounded-full border border-slate-200/20 bg-slate-900 px-4 py-2">Model: {model_label}</span>
                        <span class="rounded-full border border-slate-200/20 bg-slate-900 px-4 py-2">Alert level: <span class="font-semibold text-white">{alert_level}</span></span>
                        <span class="rounded-full border border-slate-200/20 bg-slate-900 px-4 py-2">Updated: {alert_updated}</span>
                    </div>
                </div>
                <aside class="relative rounded-3xl border border-slate-200/20 bg-slate-900/90 p-5 shadow-2xl animate-floaty" aria-label="Stadium pulse summary">
                    <div class="mb-4 flex items-center justify-between">
                        <div>
                            <p class="text-xs uppercase tracking-[0.35em] text-sky-200">Stadium pulse</p>
                            <p class="mt-1 text-2xl font-bold text-white">Operations snapshot</p>
                        </div>
                        <div class="rounded-2xl border border-slate-200/20 bg-slate-950/90 px-3 py-2 text-right">
                            <p class="text-[11px] uppercase tracking-[0.3em] text-slate-300">Status</p>
                            <p class="text-sm font-semibold text-white">{alert_level}</p>
                        </div>
                    </div>
                    <div class="grid grid-cols-2 gap-3">
                        <div class="rounded-2xl border border-slate-200/20 bg-slate-950/90 p-4">
                            <p class="text-xs uppercase tracking-[0.25em] text-slate-300">Active gates</p>
                            <p class="mt-2 text-3xl font-black text-white">{context['total_gates']}</p>
                        </div>
                        <div class="rounded-2xl border border-slate-200/20 bg-slate-950/90 p-4">
                            <p class="text-xs uppercase tracking-[0.25em] text-slate-300">Concessions</p>
                            <p class="mt-2 text-3xl font-black text-white">{context['total_concessions']}</p>
                        </div>
                        <div class="rounded-2xl border border-slate-200/20 bg-slate-950/90 p-4">
                            <p class="text-xs uppercase tracking-[0.25em] text-slate-300">Sections</p>
                            <p class="mt-2 text-3xl font-black text-white">{context['total_sections']}</p>
                        </div>
                        <div class="rounded-2xl border border-slate-200/20 bg-slate-950/90 p-4">
                            <p class="text-xs uppercase tracking-[0.25em] text-slate-300">Incidents</p>
                            <p class="mt-2 text-3xl font-black text-white">{len(context['recent_incidents'])}</p>
                        </div>
                    </div>
                    <p class="mt-4 text-sm leading-6 text-slate-200">{alert_message}</p>
                </aside>
            </div>
        </section>

        <section class="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]" aria-label="Live stadium operations panels">
            <div class="space-y-6">
                <section class="rounded-3xl border border-slate-200/20 bg-slate-950/90 p-6 shadow-glow backdrop-blur-xl" aria-labelledby="stats-title">
                    <div class="flex items-center justify-between">
                        <div>
                            <p class="text-xs uppercase tracking-[0.35em] text-emerald-200">Live stadium stats</p>
                            <h2 id="stats-title" class="mt-2 text-2xl font-bold text-white">Gates, concessions, and crew state</h2>
                        </div>
                        <div class="text-right text-sm text-slate-200">
                            <p>Accessible gates: <span class="font-semibold text-white">{len(context['active_gates'])}</span></p>
                            <p>Available crews: <span class="font-semibold text-white">{context['crew_status_counts'].get('available', 0)}</span></p>
                        </div>
                    </div>
                    <div class="mt-6 grid gap-4 md:grid-cols-2">
                        <div class="rounded-2xl border border-slate-200/20 bg-slate-900/90 p-4">
                            <p class="text-sm font-semibold text-white">Gate map</p>
                            <div class="mt-3 space-y-3">
                                {''.join(f'<div class="flex items-center justify-between rounded-xl border border-slate-200/20 bg-slate-950 px-3 py-2"><span class="font-medium text-slate-50">{escape(gate.name)}</span><span class="text-xs text-emerald-200">{"Accessible" if gate.accessible else "Standard"}</span></div>' for gate in context['active_gates'])}
                            </div>
                        </div>
                        <div class="rounded-2xl border border-slate-200/20 bg-slate-900/90 p-4">
                            <p class="text-sm font-semibold text-white">Fastest concessions</p>
                            <div class="mt-3 space-y-3">
                                {''.join(f'<div class="flex items-center justify-between rounded-xl border border-slate-200/20 bg-slate-950 px-3 py-2"><div><p class="font-medium text-slate-50">{escape(item["name"])}</p><p class="text-xs text-slate-300">{escape(item["notes"])}</p></div><span class="rounded-full bg-sky-400/10 px-3 py-1 text-sm font-semibold text-sky-200">{item["wait_minutes"]}m</span></div>' for item in context['top_concessions'])}
                            </div>
                        </div>
                    </div>
                    <div class="mt-4 grid gap-3 sm:grid-cols-4">
                        {''.join(f'<div class="rounded-2xl border border-slate-200/20 bg-slate-950/90 p-4"><p class="text-xs uppercase tracking-[0.25em] text-slate-300">{escape(status.replace("_", " "))}</p><p class="mt-2 text-2xl font-black text-white">{count}</p></div>' for status, count in context['crew_status_counts'].items())}
                    </div>
                </section>

                <section class="rounded-3xl border border-slate-200/20 bg-slate-950/90 p-6 shadow-glow backdrop-blur-xl" aria-labelledby="fan-chat-title">
                    <div class="flex items-center justify-between">
                        <div>
                            <p class="text-xs uppercase tracking-[0.35em] text-sky-200">Fan Assistant</p>
                            <h2 id="fan-chat-title" class="mt-2 text-2xl font-bold text-white">Interactive chat tester</h2>
                        </div>
                        <span class="rounded-full border border-slate-200/20 bg-slate-900 px-3 py-1 text-xs uppercase tracking-[0.3em] text-slate-200">/api/fan/chat</span>
                    </div>

                    <form id="fan-form" aria-label="Fan assistant test form" class="mt-6" onsubmit="return false;">
                        <div class="grid gap-4 md:grid-cols-2">
                            <div class="block">
                                <label for="fan-ticket" class="text-sm font-medium text-slate-100">Ticket category</label>
                                <select id="fan-ticket" aria-label="Ticket category selection" class="mt-2 w-full rounded-2xl border border-slate-200/20 bg-slate-950 px-4 py-3 text-white outline-none ring-0 focus:border-sky-200">
                                    <option>general</option>
                                    <option>premium</option>
                                    <option>vip</option>
                                    <option>accessible</option>
                                    <option>family</option>
                                </select>
                            </div>
                            <div class="block">
                                <label for="fan-language" class="text-sm font-medium text-slate-100">Preferred language</label>
                                <input id="fan-language" aria-label="Preferred language input" value="en" class="mt-2 w-full rounded-2xl border border-slate-200/20 bg-slate-950 px-4 py-3 text-white outline-none ring-0 focus:border-sky-200" />
                            </div>
                            <div class="block">
                                <label for="fan-gate" class="text-sm font-medium text-slate-100">Current gate</label>
                                <input id="fan-gate" aria-label="Current gate input" value="gate-b" class="mt-2 w-full rounded-2xl border border-slate-200/20 bg-slate-950 px-4 py-3 text-white outline-none ring-0 focus:border-sky-200" />
                            </div>
                            <div class="block">
                                <label for="fan-location" class="text-sm font-medium text-slate-100">Current location (x,y)</label>
                                <input id="fan-location" aria-label="Current location input" value="8,13" class="mt-2 w-full rounded-2xl border border-slate-200/20 bg-slate-950 px-4 py-3 text-white outline-none ring-0 focus:border-sky-200" />
                            </div>
                        </div>

                        <div class="mt-4 block">
                            <label for="fan-question" class="text-sm font-medium text-slate-100">Question</label>
                            <textarea id="fan-question" aria-label="Fan assistant question input" rows="4" class="mt-2 w-full rounded-2xl border border-slate-200/20 bg-slate-950 px-4 py-3 text-white outline-none ring-0 focus:border-sky-200">Where is the fastest accessible route to food and my section?</textarea>
                        </div>

                        <div class="mt-4 flex flex-wrap gap-3">
                            <button id="fan-send" type="submit" aria-label="Send fan assistant request" class="rounded-2xl bg-emerald-400 px-5 py-3 font-semibold text-slate-950 transition hover:brightness-110">Send to Fan Assistant</button>
                            <button id="fan-example" type="button" aria-label="Load fan assistant route example" class="rounded-2xl border border-slate-200/20 bg-slate-900 px-5 py-3 font-semibold text-white transition hover:bg-slate-800">Load route example</button>
                        </div>

                        <pre id="fan-response" aria-live="polite" aria-label="Fan assistant response output" class="mt-5 min-h-40 overflow-auto rounded-3xl border border-slate-200/20 bg-slate-950 p-4 text-sm leading-6 text-slate-100">Fan Assistant responses will appear here.</pre>
                    </form>
                </section>
            </div>

            <div class="space-y-6">
                <section class="rounded-3xl border border-slate-200/20 bg-slate-950/90 p-6 shadow-glow backdrop-blur-xl" aria-labelledby="ops-title">
                    <div class="flex items-center justify-between">
                        <div>
                            <p class="text-xs uppercase tracking-[0.35em] text-amber-200">Operations intake</p>
                            <h2 id="ops-title" class="mt-2 text-2xl font-bold text-white">Volunteer incident log</h2>
                        </div>
                        <span class="rounded-full border border-slate-200/20 bg-slate-900 px-3 py-1 text-xs uppercase tracking-[0.3em] text-slate-200">/api/ops/incident</span>
                    </div>

                    <form id="ops-form" aria-label="Volunteer incident submission form" class="mt-6" onsubmit="return false;">
                        <div class="space-y-4">
                            <div class="block">
                                <label for="ops-volunteer" class="text-sm font-medium text-slate-100">Volunteer ID</label>
                                <input id="ops-volunteer" aria-label="Volunteer ID input" value="vol-17" class="mt-2 w-full rounded-2xl border border-slate-200/20 bg-slate-950 px-4 py-3 text-white outline-none ring-0 focus:border-amber-200" />
                            </div>
                            <div class="block">
                                <label for="ops-location" class="text-sm font-medium text-slate-100">Location (x,y)</label>
                                <input id="ops-location" aria-label="Incident location input" value="4,5" class="mt-2 w-full rounded-2xl border border-slate-200/20 bg-slate-950 px-4 py-3 text-white outline-none ring-0 focus:border-amber-200" />
                            </div>
                            <div class="block">
                                <label for="ops-severity" class="text-sm font-medium text-slate-100">Severity hint</label>
                                <select id="ops-severity" aria-label="Severity hint selection" class="mt-2 w-full rounded-2xl border border-slate-200/20 bg-slate-950 px-4 py-3 text-white outline-none ring-0 focus:border-amber-200">
                                    <option value="">auto</option>
                                    <option>low</option>
                                    <option>medium</option>
                                    <option>high</option>
                                    <option>critical</option>
                                </select>
                            </div>
                            <div class="block">
                                <label for="ops-report" class="text-sm font-medium text-slate-100">Incident report</label>
                                <textarea id="ops-report" aria-label="Incident report input" rows="5" class="mt-2 w-full rounded-2xl border border-slate-200/20 bg-slate-950 px-4 py-3 text-white outline-none ring-0 focus:border-amber-200">Major spill near the south concourse creating a slip hazard and crowd slowdown.</textarea>
                            </div>
                        </div>

                        <div class="mt-4 flex flex-wrap gap-3">
                            <button id="ops-send" type="submit" aria-label="Submit volunteer incident" class="rounded-2xl bg-amber-300 px-5 py-3 font-semibold text-slate-950 transition hover:brightness-110">Submit Incident</button>
                            <button id="ops-example" type="button" aria-label="Load crowd bottleneck incident example" class="rounded-2xl border border-slate-200/20 bg-slate-900 px-5 py-3 font-semibold text-white transition hover:bg-slate-800">Load crowd bottleneck example</button>
                        </div>

                        <pre id="ops-response" aria-live="polite" aria-label="Operations incident response output" class="mt-5 min-h-40 overflow-auto rounded-3xl border border-slate-200/20 bg-slate-950 p-4 text-sm leading-6 text-slate-100">Incident responses will appear here.</pre>
                    </form>
                </section>

                <section class="rounded-3xl border border-slate-200/20 bg-slate-950/90 p-6 shadow-glow backdrop-blur-xl" aria-labelledby="incident-log-title">
                    <div class="flex items-center justify-between">
                        <div>
                            <p class="text-xs uppercase tracking-[0.35em] text-rose-200">Incident monitor</p>
                            <h2 id="incident-log-title" class="mt-2 text-2xl font-bold text-white">Incoming volunteer activity</h2>
                        </div>
                        <span class="rounded-full border border-slate-200/20 bg-slate-900 px-3 py-1 text-xs uppercase tracking-[0.3em] text-slate-200">Live log</span>
                    </div>
                    <div id="incident-log" role="log" aria-live="polite" aria-label="Incoming volunteer incident activity log" class="mt-5 space-y-3">
                        {recent_incident_cards}
                    </div>
                </section>
            </div>
        </section>

        <footer class="mt-8 rounded-3xl border border-slate-200/20 bg-slate-950/90 px-6 py-4 text-sm text-slate-200 shadow-glow backdrop-blur-xl" role="contentinfo">
            <p>Accessible dashboard controls mirror the same live stadium state used by the FastAPI JSON endpoints.</p>
        </footer>
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
            const card = document.createElement('article');
            card.className = 'rounded-2xl border border-slate-200/20 bg-slate-900/90 p-4';
            card.innerHTML = `
                <div class="flex items-center justify-between gap-4">
                    <h3 class="font-semibold text-white">${{escapeHtml(item.incident_type || 'incident')}}</h3>
                    <span class="text-xs text-slate-300">${{escapeHtml(item.severity || 'low')}}</span>
                </div>
                <p class="mt-2 text-sm text-slate-200">${{escapeHtml(item.report || '')}}</p>`;
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
                severity: incident.severity
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
