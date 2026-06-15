# Planning & Design Rationale

## Why build a small engine instead of adopting one

The mature CEP engines — Esper, FlinkCEP, Drools, Siddhi — are all JVM. A
genuinely Python-native CEP engine barely exists in maintained form. For a
Python-centric lab whose goal is to *understand and demonstrate* correlation,
wrestling a JVM stream cluster is the wrong first step. So:

- **Lab/demo runtime:** a ~150-line deterministic Python engine you can read and
  audit. This repo.
- **Named scale-up path:** Flink CEP / Drools — explicitly *what TeMIP runs* — so
  the conversation has a credible "and here's how it scales" answer.

This is a deliberate trade: we give up out-of-the-box scale to gain
transparency, zero licence cost, and a correlator that fits in your head.

## The correlation model

Correlation here is **not** naive "parent is down → mute the children". It is a
reachability question:

> Given the set of devices currently reporting a hard failure (`NODE_DOWN`),
> which other devices can no longer reach **any** core? Those are symptoms. The
> nearest failed device on a symptom's blocked path is its root cause.

That single definition produces the right answer for three distinct topologies
without special-casing:

| Topology | Behaviour | Why |
|---|---|---|
| **Spur (unprotected chain)** | head failure cascades to all below it | single path to core, removed |
| **RSTP ring** | one member failing suppresses *nothing* | peers keep their own gateway path |
| **Dual-homing / dual core** | single failure suppresses nothing | alternate path still reaches a core |

The dependency graph carries the redundancy as *real alternate edges*, so
resilience falls out of the reachability check rather than being encoded as a
rule. That's the property that makes the demo persuasive: the engine "knows"
RSTP protects the ring because the graph says the peers can still get home.

### FRR / RSTP modelling note

"RSTP rings of FRR switches" is not literally possible — FRR is an L3 routing
suite with no spanning tree. In the model, rings are *RSTP-protected L2 segments*;
on real containers/hardware that's a switch NOS (SR Linux, cEOS, Cumulus) or a
Linux bridge + `mstpd`, with FRR/OSPF on the routed core and spurs. The
correlation logic is independent of how the ring is realised — it only needs to
know the ring members share protection, which the dependency graph encodes.

## Rules as data

`sidecar/rules.yaml` holds two rules — `topology_reachability` and
`flap_dampening` — as declarative parameters, not code. This is the open-source
equivalent of a UCA EBC Drools ruleset: version-controlled, diffable, reviewable
in a PR. The richer UI roadmap turns this YAML into a React Flow node graph so
rules can be authored and visualised graphically.

## Same rule, three runtimes (the scaling story)

| Tier | Runtime | Throughput | When |
|---|---|---|---|
| Lab / regional NOC | this Python sidecar | thousands/s, single process | the demo; most real deployments |
| Mid / national | Python + Redis (shared window, N workers) | tens of thousands/s | larger estates |
| Carrier core | Kafka + Flink CEP **or** Drools cluster | millions/s | the only tier that may justify a commercial FM platform |

The correlation *semantics* are identical at every tier — a reachability join
over a dependency graph within a time window. Only the runtime changes.

## Performance visualisation split

- **Web UI (Cytoscape):** qualitative — the live topology, alarms lighting nodes,
  symptoms collapsing under a root cause. This is the emotional centre of the demo.
- **Grafana (Prometheus):** quantitative — suppression ratio, correlation latency,
  ingest rate, alarm-state stacks. This is the credibility.
- **Back into Zabbix:** push headline metrics via `zabbix_sender` so the platform
  the audience already trusts is monitoring the correlation layer itself.

## Zabbix 8.0 changes the picture — and the sidecar's job

Zabbix 8.0 LTS (in alpha at time of writing, expected mid-2026) ships a **native
Complex Event Processing engine** under Data collection → Event processing. It
builds on the existing event model and adds multi-event evaluation over time
windows, with tag/host-group conditions and operations that distinguish a
**cause** from its **symptoms** — suppress a symptom, change severity, retag,
rename, or stop further rule processing. Custom logic is **JavaScript**, not a
rules engine like Drools (Zabbix server is C with an embedded JS runtime; Drools
is JVM and would be architecturally alien). HPE/OpenText TeMIP's UCA EBC *is*
Drools — so the "you don't need a Drools platform" argument now has Zabbix itself
delivering deterministic CEP natively, for free.

This means the generic half of this sidecar — windowing, dedup, flap dampening,
symptom suppression — is becoming a **native Zabbix feature**. Pretending
otherwise would make the repo look naive. Instead, the sidecar should be
**repositioned to the one thing 8.0 still can't derive on its own**: *which
device is a symptom of which*, computed automatically from the Nautobot topology
graph. Zabbix 8.0 gives you the correlation engine but still expects you to tell
it cause-vs-symptom by hand via tags and host-group rules. The sidecar generates
that relationship from reachability and hands it back as tags.

### Revised architecture (post-8.0)

```
Nautobot ──topology (GraphQL)──► CEP sidecar (/classify)
                                      ▲   │ cep_role=symptom, cep_root=<device>
                          failed-host │   ▼ (tags)
                              set      │
Zabbix 8.0 ─native CEP rule (JS callout)─► attaches tags ─► native CEP
  problems        enrichment                                 suppression rule
                                                             (cause/symptom)
```

- **Zabbix 8.0 owns:** problem lifecycle, time windows, dedup, the actual
  suppression and severity changes — all native.
- **Sidecar owns:** `POST /classify {device, failed[]}` → `cep_role` +
  `cep_root` tags, a pure stateless function of the dependency graph. Zabbix
  remains the system of record for problem state; the sidecar holds no event
  state, only the topology.
- **Integration:** a native CEP rule's JS callout posts the event's host plus the
  currently-active down-set to `/classify`, attaches the returned tags, and a
  second native rule suppresses anything tagged `cep_role=symptom`. See
  `zabbix/zabbix8_cep_enrichment.js`.

The engine in `sidecar/cep/` keeps its full windowed correlation for the
standalone demo (and for pre-8.0 Zabbix), but the strategic, durable surface is
the thin `/classify` enrichment endpoint. If 8.0 ever grows native source-of-truth
topology ingestion, even that shrinks — and that's fine: the goal was always to
show the capability is commodity, not to sell a sidecar.

## Roadmap

- [ ] React Flow rule editor + live-correlation view (richer than the Cytoscape UI)
- [ ] Redis-backed sliding window for multi-worker horizontal scale
- [ ] Generic N-stage rule patterns beyond the two shipped
- [ ] Load harness emitting sustained event rates for latency percentiles
- [ ] Real containerlab fault injection wired to Zabbix triggers → sidecar webhook
- [ ] CLEAR/recovery handling and symptom re-evaluation on partial restoration

## Open questions

- Attribution when multiple independent failures share descendants — current model
  picks the nearest failed ancestor; is "nearest" always the operator's intuition?
- Whether to derive the dependency graph live from Nautobot GraphQL on each topology
  change vs. periodic cache refresh (current approach loads `topology.json` at boot).
