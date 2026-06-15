#!/usr/bin/env python3
"""
add_trap_items.py — PATH A wiring: add SNMP-trap items + triggers to the demo
hosts so received traps become Zabbix problems that the webhook forwards.

Reads the SAME trapsim/traps.yaml registry, so item OIDs and cep_kind tags stay
in sync with what send_trap.py emits. For each monitored host it creates, per
trap definition:
  * an item   snmptrap["<trapOID>"]   (type SNMP trap, Text)
  * a trigger tagged  cep_kind=<KIND>  so the webhook maps it without name-guessing

    export ZBX_URL=http://localhost/api_jsonrpc.php
    export ZBX_TOKEN=<api token>
    python add_trap_items.py

NOTE: Zabbix matches a trap to a host by the `ZBXTRAP <address>` source IP, so each
host needs an SNMP interface with that IP (populate_zabbix.py already adds one).
Because the trap *simulator* sends from a single host IP, a sim-driven path-A demo
will land all traps on whichever host owns that IP — see zabbix-path/README.md for
the single-collector-host option. With real devices, per-host matching just works.
Trigger expressions/recovery often need tuning per environment; these are sensible
defaults with manual close.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

import yaml

URL = os.environ.get("ZBX_URL", "http://localhost/api_jsonrpc.php")
TOKEN = os.environ.get("ZBX_TOKEN")
HERE = os.path.dirname(os.path.abspath(__file__))
REG = yaml.safe_load(open(os.path.join(HERE, "..", "traps.yaml")))
TOPO = os.path.join(HERE, "..", "..", "topology", "topology.json")

SEV = {"LINK_DOWN": 3, "LINK_UP": 1, "RESTART": 2, "VENDOR_ALARM": 4,
       "VENDOR_CLEAR": 1, "SECURITY": 2}   # Zabbix trigger priority

_id = 0


def call(method, params):
    global _id
    _id += 1
    body = json.dumps({"jsonrpc": "2.0", "method": method,
                       "params": params, "id": _id}).encode()
    headers = {"Content-Type": "application/json-rpc",
               "Authorization": f"Bearer {TOKEN}"}
    req = urllib.request.Request(URL, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as r:
        res = json.load(r)
    if "error" in res:
        raise RuntimeError(f"{method}: {res['error']}")
    return res["result"]


def trap_defs():
    out = []
    for name, s in REG.get("standard", {}).items():
        out.append((name, s["oid"], s["cep_kind"]))
    for name, s in REG.get("enterprise", {}).get("traps", {}).items():
        out.append((name, s["oid"], s["cep_kind"]))
    return out


def main():
    if not TOKEN:
        sys.exit("set ZBX_TOKEN")
    model = json.load(open(TOPO))
    defs = trap_defs()
    made_i = made_t = 0

    for d in model["devices"]:
        if d["layer"] == "passive" or "snmp" not in d.get("monitoring", []):
            continue
        hosts = call("host.get", {"filter": {"host": [d["name"]]},
                                  "selectInterfaces": ["interfaceid", "type"]})
        if not hosts:
            print(f"  ! {d['name']} not in Zabbix yet (run populate_zabbix.py first)")
            continue
        host = hosts[0]
        snmp_if = next((i["interfaceid"] for i in host.get("interfaces", [])
                        if i["type"] == "2"), None)
        if not snmp_if:
            print(f"  ! {d['name']} has no SNMP interface; skipping")
            continue

        for name, oid, kind in defs:
            key = f'snmptrap["{oid}"]'
            if not call("item.get", {"hostids": host["hostid"],
                                     "filter": {"key_": [key]}}):
                call("item.create", {
                    "name": f"trap {name}", "key_": key, "hostid": host["hostid"],
                    "type": 17, "value_type": 4, "interfaceid": snmp_if})
                made_i += 1
            # trigger
            expr = f'length(last(/{d["name"]}/{key}))>0'
            tname = f"{name} trap on {{HOST.NAME}}"
            if not call("trigger.get", {"hostids": host["hostid"],
                                        "filter": {"description": [tname]}}):
                call("trigger.create", {
                    "description": tname, "expression": expr,
                    "priority": SEV.get(kind, 2),
                    "manual_close": 1,
                    "tags": [{"tag": "cep_kind", "value": kind},
                             {"tag": "cep", "value": "demo"}]})
                made_t += 1
        print(f"  + {d['name']}: trap items/triggers ensured")

    print(f"Done: {made_i} items, {made_t} triggers across the SNMP hosts.")
    print("Point traps at the snmptraps container (udp/162); problems will fire and "
          "the webhook (cep_kind tag) forwards device+kind to the sidecar.")


if __name__ == "__main__":
    main()
