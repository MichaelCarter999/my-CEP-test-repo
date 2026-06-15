# CEP — Deterministic Alarm Correlation Demo

A working, open-source demonstration of **topology-aware root-cause alarm
correlation** — the capability platforms like HPE/OpenText TeMIP (+ UCA EBC) sell
as a carrier-grade product — built from Zabbix, Nautobot, a small Python CEP
sidecar, and Grafana.

The thesis: **deterministic complex correlation is a reachability computation over
a dependency graph, not a six-figure platform.** This repo proves it on a laptop.

## What's in the box

| Area | Path | What it does |
|---|---|---|
| Topology source of truth | `topology/generate_topology.py` | Defines the 35-node network → `topology.json` / `.yaml` |
| Lab generator | `topology/emit_containerlab.py` | Derives `cep-demo.clab.yml` (one FRR container per device) |
| CEP engine | `sidecar/cep/` | Reachability-based correlation (`graph.py`, `engine.py`, `models.py`) |
| Sidecar API | `sidecar/app.py` | FastAPI: `/events`, `/snapshot`, `/topology`, `/metrics`, `/ws` |
| Rules | `sidecar/rules.yaml` | `topology_reachability` + `flap_dampening` (data, not code) |
| Fault simulator | `simulator/simulate.py` | Named scenarios driving real devices |
| Real fault lab | `faultlab/` | Runnable FRR thin slice + monitor + injector — real `docker stop` → correlation |
| Trap simulator | `trapsim/` | Pure-Python SNMPv2c trap sender + receiver; standard MIB-II/IF-MIB traps, Actelis section parameterised |
| Nautobot loader | `nautobot/populate_nautobot.py` | Devices, interfaces, cables, patch panels, dependency relationship |
| Zabbix loader | `zabbix/populate_zabbix.py` | Hosts with Agent2 + SNMP interfaces, role tags |
| Live UI | `webui/index.html` | Self-contained Cytoscape NOC view: topology + live correlation + scenario buttons |
| Rule editor | `webui/rule-editor.html` | React Flow node-graph editor — author rules visually, export the engine's `rules.yaml` |
| Metrics | `grafana/`, `docker/prometheus.yml` | Prometheus scrape + provisioned Grafana performance dashboard |
| Tests | `tests/test_correlation.py` | Executable spec for every correlation claim |
| Rich report | `reporting/render_report.py` | Polished self-contained HTML test report |
| Docs + deck | `docs/` | QUICKSTART, PLANNING, ARCHITECTURE, NAUTOBOT-VS-NETBOX, SALES-PITCH + `CEP-Sales-Pitch.pptx` |

## The demo network (35 nodes)

```
        core01 ═══ core02            dual L3 core (FRR/OSPF, redundant mesh)
       ╱   │   ╲                     each dist dual-homed to BOTH cores
   dist01 dist02 dist03              L3 distribution, one per access ring
      │      │      │
   [Ring A][Ring B][Ring C]          L2 access rings, RSTP-protected, 6 nodes each
      │             │
   spur-a*        spur-c*            unprotected FRR chains off ring members
```

- 2 core · 3 distribution · 3 patch panels (passive) · 18 access (3 rings of 6) · 9 spur
- **Rings are RSTP-protected**: losing one ring switch does not isolate its peers,
  so peer alarms must *not* be suppressed. The engine gets this right because it
  asks "can this device still reach a core?", not "is its parent down?".
- **Spurs are unprotected chains**: a head failure cascades cleanly — textbook RCA.

## Architecture

```
Nautobot ──topology + dependency (GraphQL)──┐
                                             ▼
clab faults / simulator ─► Zabbix ─webhook─► CEP sidecar ─/metrics─► Prometheus ─► Grafana
                                             │
                                             └─WebSocket─► live correlation UI
```

## Quick start

```bash
make gen        # regenerate topology.json + cep-demo.clab.yml
make sidecar    # run the CEP sidecar (FastAPI on :8080)
make sim S=dist_blackhole   # fire a scenario, watch correlation
make test       # pytest
make report     # render reporting/report.html
```

See [`docs/QUICKSTART.md`](docs/QUICKSTART.md) for the full bring-up (containerlab,
Nautobot, Zabbix). The argument for SAs is in [`docs/SALES-PITCH.md`](docs/SALES-PITCH.md)
and `docs/CEP-Sales-Pitch.pptx`; design rationale is in [`docs/PLANNING.md`](docs/PLANNING.md).

## Two modes

The sidecar runs in either of two modes depending on your Zabbix version:

- **Standalone correlation (Zabbix ≤ 7.x):** the sidecar does the full windowed
  correlation — ingest, suppress, dedup, flap dampening — and drives the UI.
- **Topology-enrichment (Zabbix 8.0+):** Zabbix's *native* CEP engine owns the
  windows, dedup and suppression; the sidecar narrows to one stateless call,
  `POST /classify`, that returns topology-derived `cep_role`/`cep_root` tags for
  Zabbix to act on. This is the durable role once 8.0 ships native CEP — see
  [`docs/PLANNING.md`](docs/PLANNING.md) and `zabbix/zabbix8_cep_enrichment.js`.

## Status

- [x] Topology model + generator + containerlab emitter
- [x] Reachability CEP engine + rules + Prometheus metrics + WebSocket
- [x] Fault simulator (7 scenarios incl. throughput storm)
- [x] Nautobot + Zabbix loaders
- [x] pytest suite (7/7) + rich HTML report
- [x] Cytoscape live-correlation UI (`webui/`) + scenario controls
- [x] Grafana performance dashboard + Prometheus scrape committed under `grafana/`
- [x] Real fault-injection thin slice (`faultlab/`) — FRR/OSPF + monitor + injector, verified end-to-end
- [x] React Flow rule editor (`webui/rule-editor.html`) — author rules as a node graph → `rules.yaml`
- [x] SNMP trap simulator (`trapsim/`) — both paths: direct (`trapd.py`) and realistic via Zabbix (`zabbix-path/`); standard MIB-II/IF-MIB traps done, Actelis section parameterised
- [ ] SR-OS (SR-SIM) ring lab for a real multi-vendor L2 story — planned
- [ ] Fold the Actelis ML-540 traps into `trapsim/traps.yaml` once the MIB is supplied

> **Naming note:** "RSTP rings of FRR switches" isn't literally possible — FRR is
> L3-only with no spanning tree. The rings are modelled as RSTP-protected L2 paths;
> on real hardware/containers that's a switch NOS or Linux bridge + `mstpd`, with
> FRR/OSPF for the routed core and spurs. See `docs/PLANNING.md`.
