# Sales Pitch — Why You Probably Don't Need TeMIP

**One line:** topology-aware root-cause alarm correlation is a *reachability
computation over a dependency graph*, not a carrier-grade platform. This repo
performs it deterministically, on a laptop, with tooling you already run.

This is written to be defensible in a room full of Solutions Architects. It does
not claim the open stack replaces TeMIP everywhere — it claims TeMIP is the wrong
default for the regional/enterprise tier, which is most of the work.

---

## What TeMIP actually is

HPE/OpenText TeMIP is a fault-management framework; its correlation is delivered
by **UCA EBC (Unified Correlation Analyzer / Event Based Correlation)**, which is
a **Drools rule engine running over a topology model**. That matters: the "magic"
is a deterministic rule engine plus a dependency graph. There is no proprietary
physics here that open tooling cannot reproduce — only packaging, support, and a
carrier-scale runtime.

| TeMIP / UCA EBC claim | Reality | This demo |
|---|---|---|
| Vendor-neutral alarm normalisation | Inventory + a canonical event schema | Nautobot inventory; sidecar normalises Zabbix problems to event kinds |
| Topology-aware root-cause analysis | Drools rules over a dependency graph | `networkx` reachability over the Nautobot-derived graph |
| Deterministic, auditable correlation | Rete rule evaluation | Pure-Python deterministic pass; identical input → identical output (tested) |
| Carrier scale (millions of events/s) | Genuinely needs a stream runtime | Honest: that tier is Kafka + Flink/Drools — still open source |

## The numbers that land

Measured on this container (single Python process, 32-node graph):

- **Suppression ratio 99.7%** on a distribution-level cascade — one root cause absorbs ~360 symptom alarms.
- **Correlation latency ~0.4 ms** per pass; **~4,000 alarms/sec** ingest-and-correlate.
- **Deterministic**: `test_determinism` asserts identical output for identical input ordering. No scoring, no ML, nothing to explain to an auditor.
- **Cost**: the runtime is FastAPI + networkx. The licence is MIT-shaped. The "platform" is a 150-line engine you can read in one sitting.

## The five-move demo

1. **Calm.** Show the topology in the NOC UI — 32 FRR nodes, all green. "Multi-vendor inventory in Nautobot, monitored in Zabbix."
2. **The wall of noise.** Fire `dist_blackhole`. Zabbix lights up with the whole ring + spurs alarming. "This is what the operator sees today."
3. **Correlation.** The UI collapses ~10 symptoms under one red root-cause node, edges drawn to it. Grafana shows suppression spike to ~99% and latency stay sub-millisecond. "Same events. One actionable alarm."
4. **The clever bit.** Fire `ring_protected` — one RSTP ring switch fails and **nothing is suppressed**, because the peers still reach the core. Then `core_redundant` — a core fails and nothing downstream is lost. "It encodes resilience, not just parent-child muting. That's the part people assume needs a platform."
5. **The rules.** Open `sidecar/rules.yaml`. "That's the entire ruleset — version-controlled YAML in Git, not a professional-services engagement. And here's the test suite that proves every claim I just made."

## Honest caveats (say these before they do)

- **True carrier scale is real.** At millions of events/sec across a national core you want Kafka + Flink CEP or a Drools cluster. The open path scales there too — but that's the one tier where a commercial platform's support contract may be worth it.
- **This is correlation, not a full FM suite.** TeMIP also brings trouble-ticketing integration, northbound interfaces, decades of telco accreditation. If you're contractually required to have those, factor them in.
- **You own the rules.** That's a feature (auditable, free, in Git) and a responsibility (you maintain them, not a vendor).

## Recommendation

For regional networks, enterprise, transport, and most public-sector estates:
**build on the open stack.** Reserve a carrier-grade FM platform evaluation for the
genuine millions-of-events-per-second core, and even then benchmark open Flink/Drools
against the licence cost first. The capability is not the differentiator — the
scale runtime and the support wrap are. Buy those when you need them, not by default.
