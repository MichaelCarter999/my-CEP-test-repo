# Fault lab — real fault injection (thin slice)

A minimal, runnable proof that the whole chain works on *real* FRR containers, not
simulated events: **`docker stop` a node → real OSPF withdrawal → the monitor
detects it → sidecar correlates → one root cause, the rest suppressed.**

Routed-only (all FRR/OSPF, no L2 rings) so it's light enough for a laptop and the
faults are genuine. It reuses real device names from the main topology, so the
existing sidecar graph correlates it with **zero changes**.

```
core01 ═ core02        dual core (OSPF); dist01 dual-homed -> redundancy demo
    ╲   ╱
    dist01
    ╱    ╲
acc-a1   acc-a4         acc-a1 = sibling leaf (must survive spur faults)
             │
          spur-a1 ─ spur-a2 ─ spur-a3   unprotected chain -> cascade demo
```

A `probe` (alpine) attached to core01 pings every node's loopback over the OSPF
data plane — so when an upstream node dies, the downstream loopbacks really do
become unreachable (route withdrawn), exactly as a NOC would observe.

## Prerequisites

WSL2 / Ubuntu 24.04 with Docker + containerlab. ~9 light containers (8 FRR +
probe); a few GB RAM is plenty (far less than the full 32-node lab).

## Run it

```bash
# 1. generate the topology + FRR configs
python faultlab/generate_faultlab.py

# 2. deploy the real network
cd faultlab && sudo containerlab deploy -t faultlab.clab.yml && cd ..

# 3. start the sidecar (uses the main topology.json — same graph)
cd sidecar && TOPOLOGY_FILE=../topology/topology.json uvicorn app:app --port 8080 &
cd ..

# 4. start the detection agent (the Zabbix stand-in)
python faultlab/monitor.py &      # polls every 3s, posts state changes to /events

# 5. open the UI
#    webui/index.html  (or http://localhost:8088 via docker compose)
```

## Inject real faults

```bash
python faultlab/inject.py scenario spur_cascade   # stop spur-a1
# monitor detects spur-a1 NODE_DOWN + spur-a2/a3 UNREACHABLE within one poll;
# sidecar: spur-a1 = ROOT_CAUSE, spur-a2/a3 = suppressed SYMPTOMs.

python faultlab/inject.py start spur-a1           # heal -> CLEAR cascade, alarms drop
python faultlab/inject.py scenario core_single    # stop core01 -> nothing lost (redundant)
python faultlab/inject.py scenario acc_independent # stop acc-a1 -> isolated, not a symptom
python faultlab/inject.py list
```

Contrast worth showing live: `spur_cascade` collapses three alarms to one root
cause; `core_single` produces **no** suppression because dist01 still reaches
core02 — the redundancy is real OSPF reconvergence, not a scripted result.

## How detection maps to a real NOC

The monitor emits exactly what a Zabbix trigger pair would:

| Observation | Event | Zabbix equivalent |
|---|---|---|
| container stopped | `NODE_DOWN` | host ICMP/agent unavailable on the device itself |
| up but loopback unreachable from probe | `UNREACHABLE` | ICMP unreachable from a remote prober |
| recovered | `CLEAR` | problem resolved |

So `monitor.py` is a drop-in stand-in for Zabbix in the thin slice. To use **real
Zabbix 7.4** instead: point it at these hosts (ICMP + SNMP), and configure the
webhook media type (`zabbix/cep_webhook_mediatype.js`) to POST problems to the
sidecar `/events` — then stop `monitor.py`; the chain is identical.

## Verify without Docker

The detection→correlation logic is covered by `tests/test_faultlab.py`, and you
can dry-run the monitor against a mock fault state:

```bash
python faultlab/monitor.py --mock faultlab/state.example.json --once
```

## Teardown

```bash
cd faultlab && sudo containerlab destroy -t faultlab.clab.yml --cleanup
```

## Notes / honesty

- **Routed-only by design.** FRR has no spanning tree, so this slice models
  protection as redundant routed paths (the dual core), not literal RSTP. The
  full L2-ring story (mstpd / SR Linux) is a separate, heavier exercise — see
  `docs/PLANNING.md`.
- The probe pings loopbacks **over the data plane** on purpose; pinging the
  containerlab management network would show downstream nodes as still up (mgmt
  is out-of-band) and you'd see no cascade.
