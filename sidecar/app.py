"""
app.py — CEP sidecar HTTP/WS surface.

Endpoints:
    POST /events           ingest one alarm (Zabbix webhook or simulator)
    POST /events/batch     ingest many
    GET  /snapshot         current correlated state (alarms + metrics)
    GET  /topology         the dependency graph (nodes + edges) for the UI
    GET  /metrics          Prometheus exposition
    POST /clear            reset state
    WS   /ws               live snapshot stream (pushed on every change)
"""
from __future__ import annotations

import asyncio
import os
import time
import uuid

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from cep.engine import CEPEngine
from cep.graph import DependencyGraph
from cep.models import Alarm

TOPO = os.environ.get("TOPOLOGY_FILE", "/app/topology.json")
WINDOW_S = float(os.environ.get("CEP_WINDOW_S", "60"))

graph = DependencyGraph.from_file(TOPO)
engine = CEPEngine(graph, window_s=WINDOW_S)

app = FastAPI(title="CEP Sidecar", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])

_clients: set[WebSocket] = set()


class EventIn(BaseModel):
    device: str
    kind: str                       # NODE_DOWN | UNREACHABLE | IF_FLAP | ...
    severity: str = "high"
    interface: str | None = None
    ts: float | None = None
    source: str = "sim"
    id: str | None = None


def _to_alarm(e: EventIn) -> Alarm:
    return Alarm(
        id=e.id or f"{e.device}:{e.kind}:{uuid.uuid4().hex[:8]}",
        device=e.device, kind=e.kind, severity=e.severity,
        interface=e.interface, ts=e.ts or time.time(), source=e.source,
    )


async def _broadcast():
    if not _clients:
        return
    snap = engine.snapshot()
    dead = set()
    for ws in _clients:
        try:
            await ws.send_json(snap)
        except Exception:
            dead.add(ws)
    _clients.difference_update(dead)


@app.post("/events")
async def post_event(e: EventIn):
    engine.ingest(_to_alarm(e))
    await _broadcast()
    return {"ok": True, "metrics": engine.metrics.__dict__}


@app.post("/events/batch")
async def post_batch(events: list[EventIn]):
    for e in events:
        engine.ingest(_to_alarm(e))
    await _broadcast()
    return {"ok": True, "count": len(events), "metrics": engine.metrics.__dict__}


class ClassifyIn(BaseModel):
    device: str                      # the device whose problem is being evaluated
    failed: list[str] | None = None  # devices currently hard-down; omit to use
                                     # the sidecar's own webhook-fed down-set


@app.post("/classify")
async def classify(req: ClassifyIn):
    """
    Stateless topology RCA, for use as an enrichment callout from Zabbix 8.0's
    native CEP engine. Given the set of currently-failed devices and one device
    under evaluation, return whether it is a root cause, a symptom (and of what),
    or independent. Pure function of the dependency graph.

    `failed` may be supplied explicitly (fully stateless) OR omitted, in which
    case the sidecar uses the NODE_DOWN devices it has already seen via the
    Zabbix webhook (`/events`). The latter keeps the Zabbix CEP rule trivial —
    it only needs to pass the host under evaluation.

    Returns tags ready to attach to the Zabbix event:
      cep_role  = cause | symptom | independent
      cep_root  = <root-cause device>   (present only for symptoms)
    """
    if req.failed is not None:
        failed = set(req.failed)
    else:
        failed = {a.device for a in engine.alarms.values() if a.kind == "NODE_DOWN"}
    impact = graph.impacted_by(failed) if failed else {}
    dev = req.device

    if dev in failed:
        explains = [d for d, rc in impact.items() if rc == dev]
        role = "cause" if explains else "independent"
        return {"device": dev, "role": role, "root_cause": None,
                "explains": explains,
                "tags": [{"tag": "cep_role", "value": role}]}

    rc = impact.get(dev)
    if rc is not None:
        return {"device": dev, "role": "symptom", "root_cause": rc, "explains": [],
                "tags": [{"tag": "cep_role", "value": "symptom"},
                         {"tag": "cep_root", "value": rc}]}

    return {"device": dev, "role": "independent", "root_cause": None, "explains": [],
            "tags": [{"tag": "cep_role", "value": "independent"}]}


@app.get("/snapshot")
async def snapshot():
    return engine.snapshot()


@app.get("/topology")
async def topology():
    nodes = [{"id": n, **graph.g.nodes[n]} for n in graph.g.nodes]
    edges = [{"source": u, "target": v, **graph.g.edges[u, v]}
             for u, v in graph.g.edges]
    return {"nodes": nodes, "edges": edges, "cores": sorted(graph.cores)}


@app.post("/clear")
async def clear():
    engine.clear()
    await _broadcast()
    return {"ok": True}


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics():
    m = engine.metrics
    lines = [
        "# HELP cep_alarms_ingested_total Total alarms ingested",
        "# TYPE cep_alarms_ingested_total counter",
        f"cep_alarms_ingested_total {m.ingested}",
        "# HELP cep_alarms_active Active (uncorrelated) alarms",
        "# TYPE cep_alarms_active gauge",
        f"cep_alarms_active {m.active}",
        "# HELP cep_alarms_symptoms Suppressed symptom alarms",
        "# TYPE cep_alarms_symptoms gauge",
        f"cep_alarms_symptoms {m.symptoms}",
        "# HELP cep_alarms_root_causes Identified root-cause alarms",
        "# TYPE cep_alarms_root_causes gauge",
        f"cep_alarms_root_causes {m.root_causes}",
        "# HELP cep_alarms_flapping Damped flapping alarms",
        "# TYPE cep_alarms_flapping gauge",
        f"cep_alarms_flapping {m.flapping}",
        "# HELP cep_suppression_ratio Symptoms / (symptoms + root causes)",
        "# TYPE cep_suppression_ratio gauge",
        f"cep_suppression_ratio {m.suppression_ratio:.4f}",
        "# HELP cep_correlation_latency_ms Last correlation pass latency",
        "# TYPE cep_correlation_latency_ms gauge",
        f"cep_correlation_latency_ms {m.last_latency_ms:.4f}",
    ]
    return "\n".join(lines) + "\n"


@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    _clients.add(websocket)
    await websocket.send_json(engine.snapshot())
    try:
        while True:
            await asyncio.sleep(30)
            await websocket.send_json({"ping": time.time()})
    except WebSocketDisconnect:
        _clients.discard(websocket)


@app.get("/healthz")
async def healthz():
    return {"ok": True, "nodes": graph.node_count(), "window_s": WINDOW_S}
