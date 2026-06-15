# Path A — realistic SNMP traps through Zabbix

The production-faithful route: trap → Zabbix `snmptrapd` → trap log → Zabbix
SNMP-trap item → trigger → existing webhook → sidecar. Contrast with **path B**
(`trapsim/trapd.py`), which posts straight to the sidecar for a fast,
self-contained demo. Same `send_trap.py` drives both — you just change the target.

```
send_trap.py ──udp/162──▶ zabbix-snmptraps ──snmptraps.log──▶ zabbix-server
                          (snmptrapd)          (shared vol)      SNMP trapper
                                                                     │
                                          snmptrap["<oid>"] item ◀───┘
                                                     │ trigger (tag cep_kind=…)
                                                     ▼
                                          webhook media type ──▶ sidecar /events
```

## Setup

**1. Run the trap collector** (official image) alongside your Zabbix compose:

```bash
docker compose -f your-zabbix-compose.yml -f docker-compose.snmptraps.yml up -d
```

and add to your existing `zabbix-server` service (the two easily-missed bits):

```yaml
environment:
  ZBX_ENABLE_SNMP_TRAPS: "true"
volumes:
  - snmptraps:/var/lib/zabbix/snmptraps:ro
```

Without `ZBX_ENABLE_SNMP_TRAPS=true` the server never starts the SNMP trapper —
traps reach `snmptraps.log` but never become items. This is the #1 gotcha.

**2. Create the trap items + triggers** on the demo hosts:

```bash
export ZBX_URL=http://localhost/api_jsonrpc.php ZBX_TOKEN=<token>
python add_trap_items.py        # reads ../traps.yaml; items keyed by trap OID
```

**3. Wire the webhook** (already in `zabbix/cep_webhook_mediatype.js`): the trap
triggers carry a `cep_kind` tag, and the webhook now prefers that tag over
name-guessing. Pass it the tag via a media-type parameter
(`cep_kind = {EVENT.TAGS.cep_kind}`) plus `device = {HOST.HOST}`.

**4. Fire a trap** at the collector (note `:162`, not the path-B `:1162`):

```bash
python ../send_trap.py linkDown --device acc-a1 --ifindex 2 \
    --community cep-demo --target <zabbix-host>:162
```

You should see a problem on `acc-a1` in Monitoring → Problems, tagged
`cep_kind=LINK_DOWN`, and the sidecar receive the forwarded event.

## The host-matching reality (important for the simulator)

Zabbix matches a trap to a host by the `ZBXTRAP <address>` **source IP**, against
each host's SNMP interface IP. With **real devices** this is automatic — each ML-540
sends from its own IP and lands on its own host.

The **simulator** sends every trap from one machine, so all sim traps share one
source IP and would land on a single host. Two ways to demo path A with the sim:

- **Single collector host:** create one host (e.g. `cep-trap-collector`) whose SNMP
  interface = the sim's source IP, give it `snmptrap.fallback`, and let the webhook
  read the real device from the trap's `sysName.0` varbind (`send_trap.py` always
  includes it). Cleanest for a sim demo.
- **Per-host (most realistic):** run the `faultlab/` FRR containers and source traps
  from inside each container so the source IPs differ — closest to production, more
  setup.

## When you have the Actelis MIB

Nothing here changes structurally: `add_trap_items.py` re-reads `../traps.yaml`, so
once you fill the `enterprise:` block with the real Actelis trap OIDs + cep_kinds,
re-running the script adds matching items/triggers. Load the Actelis MIB into the
trap container too (`/var/lib/zabbix/mibs`) if you want symbolic names in the log.
