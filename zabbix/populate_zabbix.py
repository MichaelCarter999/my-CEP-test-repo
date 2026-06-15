#!/usr/bin/env python3
"""
populate_zabbix.py — load monitored devices into Zabbix from topology.json.

For each device with a mgmt_ip, creates a host with the interfaces its
`monitoring` list calls for:
  - "agent" -> Zabbix Agent2 interface (port 10050)
  - "snmp"  -> SNMPv2 interface (port 161)
Hosts are grouped by role (CEP/<role> and CEP/all) and tagged with
role/layer/protected so problems exported to the CEP sidecar already carry the
correlation context. Passive devices (patch panels) are skipped.

Uses the Zabbix 7.x API with bearer-token auth.

Env:
  ZBX_URL    (default http://localhost/api_jsonrpc.php)
  ZBX_TOKEN  (Zabbix UI > Users > API tokens)
  SNMP_COMMUNITY (default cep-demo-ro)
Run: python3 zabbix/populate_zabbix.py
"""
from __future__ import annotations

import json
import os
import sys

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
TOPO = os.path.join(HERE, "..", "topology", "topology.json")
URL = os.environ.get("ZBX_URL", "http://localhost/api_jsonrpc.php")
TOKEN = os.environ.get("ZBX_TOKEN", "")
COMMUNITY = os.environ.get("SNMP_COMMUNITY", "cep-demo-ro")
_id = 0

AGENT, SNMP = 1, 2


def call(method: str, params: dict):
    global _id
    _id += 1
    headers = {"Content-Type": "application/json-rpc"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    body = {"jsonrpc": "2.0", "method": method, "params": params, "id": _id}
    r = requests.post(URL, json=body, headers=headers, timeout=30)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError(f"{method}: {data['error']}")
    return data["result"]


def group_id(name: str) -> str:
    found = call("hostgroup.get", {"filter": {"name": [name]}})
    return found[0]["groupid"] if found else call("hostgroup.create", {"name": name})["groupids"][0]


def main():
    model = json.load(open(TOPO))
    print(f"Populating Zabbix at {URL}")

    roles = {d["role"] for d in model["devices"] if d.get("mgmt_ip")}
    groups = {r: group_id(f"CEP/{r}") for r in roles}
    groups["all"] = group_id("CEP/all")

    created = skipped = 0
    for d in model["devices"]:
        if not d.get("mgmt_ip") or not d.get("monitoring"):
            skipped += 1
            continue
        if call("host.get", {"filter": {"host": [d["name"]]}}):
            continue

        interfaces = []
        if "agent" in d["monitoring"]:
            interfaces.append({"type": AGENT, "main": 1, "useip": 1,
                               "ip": d["mgmt_ip"], "dns": "", "port": "10050"})
        if "snmp" in d["monitoring"]:
            interfaces.append({"type": SNMP, "main": 1, "useip": 1,
                               "ip": d["mgmt_ip"], "dns": "", "port": "161",
                               "details": {"version": 2, "community": COMMUNITY}})

        call("host.create", {
            "host": d["name"],
            "name": f"{d['name']} ({d['platform']})",
            "interfaces": interfaces,
            "groups": [{"groupid": groups[d["role"]]}, {"groupid": groups["all"]}],
            "tags": [
                {"tag": "role", "value": d["role"]},
                {"tag": "layer", "value": d["layer"]},
                {"tag": "protected", "value": str(d["protected"]).lower()},
                {"tag": "site", "value": d["site"]},
            ],
        })
        created += 1

    print(f"  hosts created: {created}   (skipped {skipped} passive/unmonitored)")
    print("  next: attach 'Linux by Zabbix agent/2' + 'Generic by SNMP' templates,")
    print("        and add the CEP webhook media type that POSTs problems to /events.")


if __name__ == "__main__":
    if not TOKEN:
        print("Set ZBX_TOKEN (Zabbix UI > Users > API tokens) for a real run.",
              file=sys.stderr)
    main()
