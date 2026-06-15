# QUICKSTART

Target: WSL2 / Ubuntu 24.04 with Docker, containerlab, and (optionally) your
existing Nautobot + Zabbix. You can demo the correlation engine in ~2 minutes
without any of the network infrastructure, then layer the real lab on top.

## Fast path — correlation engine only (no lab needed)

```bash
pip install --break-system-packages fastapi 'uvicorn[standard]' networkx pyyaml pytest requests

# 1. run the sidecar (serves the canonical topology.json)
cd sidecar && TOPOLOGY_FILE=../topology/topology.json uvicorn app:app --port 8080 &

# 2. fire scenarios and watch correlation
cd ../simulator
python simulate.py --scenario list
python simulate.py --scenario dist_blackhole   # ring gateway down -> mass suppression
python simulate.py --scenario ring_protected   # one ring node -> peers NOT suppressed
python simulate.py --scenario spur_cascade      # spur head -> clean chain cascade
python simulate.py --scenario storm --rate 400  # throughput / latency test

# 3. see correlated state + metrics
curl -s localhost:8080/snapshot | jq '.metrics'
curl -s localhost:8080/metrics            # Prometheus exposition
```

## Tests + the rich report

```bash
pytest -q                          # 7/7; conftest writes reporting/results.json
python reporting/render_report.py  # -> reporting/report.html (open or host on Pages)
```

## Full lab — containerlab

```bash
# regenerate the model + clab topology
python topology/generate_topology.py
python topology/emit_containerlab.py

cd topology && sudo containerlab deploy -t cep-demo.clab.yml
```

Drive real faults (the simulator can also be pointed at real Zabbix problems):

```bash
docker stop clab-cep-demo-spur-c1      # cascades down the spur chain
docker stop clab-cep-demo-dist03       # black-holes ring C + its spurs
docker stop clab-cep-demo-acc-a3       # ring reconverges — NO cascade (the contrast)
```

## Nautobot

```bash
export NAUTOBOT_URL=http://localhost:8080
export NAUTOBOT_TOKEN=<your-token>
python nautobot/populate_nautobot.py
```

Creates the 35 devices, interfaces, cables, the three patch panels (front/rear
ports), and the **`upstream-dependency`** relationship — the RCA source of truth
the engine reads via GraphQL.

## Zabbix

```bash
export ZBX_URL=http://localhost/api_jsonrpc.php
export ZBX_TOKEN=<api-token>
python zabbix/populate_zabbix.py
```

Then in the UI: attach *Linux by Zabbix agent/2* (agent hosts) and *Generic by
SNMP* (snmp hosts), create a webhook media type that POSTs problems to the sidecar
`/events`, and add an action sending Problem + Recovery events to it.

## Zabbix 8.0 — native CEP wiring (enrichment + suppression)

> Zabbix 8.0 is in alpha; the Event processing UI and rule-JS API may change
> before GA. This is the intended end-to-end shape — adapt field names to the
> shipped build. On Zabbix ≤ 7.x, skip this and use the standalone sidecar.

In 8.0, native CEP does the suppression; the sidecar only answers "is this host
a symptom, and of what?". Two rules under **Data collection → Event processing**,
plus the webhook you already configured so the sidecar knows what's currently down.

**Prerequisite:** the `/events` webhook + action from the Zabbix section above must
be active — that feeds the sidecar's down-set, so `/classify` works with just a host.

**Rule 1 — Enrichment** (runs first; tags the event)

- *Catch:* new problem events from the demo estate (condition: host group `CEP demo`,
  or tag `cep = demo`).
- *Type:* single-event.
- *Custom logic (JavaScript):* paste `zabbix/zabbix8_cep_enrichment.js`. It POSTs
  the host to the sidecar `/classify` and returns `cep_role` (+ `cep_root` for
  symptoms) as tags.
- *Operation:* **Add tags** from the script output.
- *Sort order:* `10` (low = early). **Do not** stop processing — Rule 2 must see it.

**Rule 2 — Suppression** (acts on the tags Rule 1 added)

- *Catch:* events with tag `cep_role = symptom`.
- *Type:* multi-event, window e.g. `60s` (so a symptom links to a cause seen in-window).
- *Operation:* mark as **Symptom** (Zabbix links it under the matching `cep_role = cause`
  event for the same `cep_root`), and **suppress** it from the problem list /
  notifications.
- *Sort order:* `20`. Set **Stop processing** so a classified symptom isn't
  re-evaluated by later rules.

**Drive it and watch**

```bash
# fire a cascade exactly as in the standalone demo
docker stop clab-cep-demo-dist03        # or: python simulator/simulate.py --scenario dist_blackhole
```

In **Monitoring → Problems** you should see one cause (`dist03`, tag `cep_role=cause`)
with the ring-C members collapsed beneath it as suppressed symptoms — produced by
Zabbix's *native* engine, with the cause/symptom relationship supplied by the
sidecar. Contrast with `docker stop clab-cep-demo-acc-a3` (a ring switch): it stays
a standalone problem because `/classify` returns `independent` (RSTP protected).

**Sanity-check the callout directly:**

```bash
curl -s localhost:8080/classify -H 'Content-Type: application/json' \
  -d '{"device":"acc-c2","failed":["dist03"]}'
# -> {"role":"symptom","root_cause":"dist03","tags":[{"tag":"cep_role",...}]}
```

## Teardown

```bash
cd topology && sudo containerlab destroy -t cep-demo.clab.yml --cleanup
```
