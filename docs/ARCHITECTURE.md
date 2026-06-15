# Architecture

## Data flow

```
                 ┌──────────────────────────────────────────────┐
                 │  topology/generate_topology.py                │
                 │  → topology.json  (SINGLE SOURCE OF TRUTH)    │
                 └───┬───────────────┬──────────────┬───────────┘
                     │               │              │
        emit_containerlab    populate_nautobot   populate_zabbix
                     │               │              │
                     ▼               ▼              ▼
            cep-demo.clab.yml    Nautobot        Zabbix hosts
            (32 FRR nodes)    (DCIM + deps)    (agent + SNMP)
                                     │              │
                                     │ GraphQL      │ webhook media type
                                     │ (topology)   │ (problems → events)
                                     ▼              ▼
                          ┌─────────────────────────────────┐
            simulator ───▶│  CEP sidecar (FastAPI, :8080)    │
            /events       │  cep/graph.py   reachability     │
                          │  cep/engine.py  windowed corr.   │
                          │  cep/models.py  Alarm types      │
                          └───┬───────────────┬──────────────┘
                              │ /metrics       │ /ws, /snapshot
                              ▼                ▼
                       Prometheus :9090   Web UI (Cytoscape)
                              │            live correlation
                              ▼
                        Grafana :3000
                        perf dashboard
```

## Components

| Component | Tech | Responsibility |
|---|---|---|
| Topology generator | Python | Emits the canonical `topology.json`; everything else reads it |
| containerlab emitter | Python → YAML | One FRR container per device, links from the cable list |
| Nautobot loader | pynautobot | DCIM (devices/interfaces/cables/panels) + dependency relationship |
| Zabbix loader | Zabbix 7.x API | Hosts with agent + SNMP interfaces, role/protected tags |
| CEP sidecar | FastAPI + networkx | Ingest, reachability correlation, metrics, WebSocket |
| Simulator | Python | Named fault scenarios + throughput storm |
| Web UI | HTML + Cytoscape.js | Live topology + correlation, scenario buttons |
| Metrics | Prometheus + Grafana | Suppression ratio, latency, ingest rate, state stacks |
| Tests | pytest | Executable spec of correlation guarantees |
| Report | Python → HTML | NOC-styled self-contained test report |

## Sidecar API

| Method | Path | Purpose |
|---|---|---|
| POST | `/events` | ingest one alarm (Zabbix webhook or simulator) |
| POST | `/events/batch` | ingest many |
| POST | `/classify` | stateless topology RCA: `{device, failed[]}` → cause/symptom + tags (Zabbix 8.0 enrichment mode) |
| GET | `/snapshot` | current correlated state (alarms + metrics) |
| GET | `/topology` | dependency graph (nodes + edges) for the UI |
| GET | `/metrics` | Prometheus exposition |
| POST | `/clear` | reset state |
| WS | `/ws` | live snapshot stream pushed on every change |
| GET | `/healthz` | liveness + node count |

## Event schema

```json
{ "device": "spur-c1", "kind": "NODE_DOWN", "severity": "high",
  "interface": null, "ts": 1718000000.0, "source": "zabbix" }
```

`kind` ∈ `NODE_DOWN | UNREACHABLE | LINK_DOWN | LINK_UP | IF_FLAP | CLEAR`.
The Zabbix webhook media type (`zabbix/cep_webhook_mediatype.js`) maps trigger
names to these kinds.

## Why a sidecar (not a Zabbix plugin)

Keeping correlation in a separate service means: it's language-appropriate
(Python + networkx), independently testable, swappable for a Flink job at scale,
and it can consume topology from Nautobot and events from Zabbix without being
coupled to either's internals. Zabbix stays the system of record for raw
problems; the sidecar is the correlation layer on top.
