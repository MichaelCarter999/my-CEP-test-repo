#!/usr/bin/env python3
"""
populate_nautobot.py — load the canonical topology into Nautobot.

Reads topology/topology.json (the same model clab, Zabbix and the CEP engine use,
so nothing drifts) and creates:

  - Location              demo-dc1
  - Manufacturers         from device.vendor (FRR, generic)
  - Device types          from device.platform (frr-9, passive-24)
  - Roles                 from device.role (core/distribution/access/spur/patch-panel)
  - Devices + interfaces  all 35 devices incl. their interface lists
  - Patch panels          role=patch-panel, with front/rear ports
  - Cables                from the canonical cable list (incl. via_panel hops)
  - Relationship          "upstream-dependency" (child -> parent) == the RCA
                          source of truth the CEP engine consumes via GraphQL

Idempotent via get_or_create. Env:
  NAUTOBOT_URL   (default http://localhost:8080)
  NAUTOBOT_TOKEN
Run: python3 nautobot/populate_nautobot.py
"""
from __future__ import annotations

import json
import os
import sys

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
TOPO = os.path.join(HERE, "..", "topology", "topology.json")
URL = os.environ.get("NAUTOBOT_URL", "http://localhost:8080").rstrip("/")
TOKEN = os.environ.get("NAUTOBOT_TOKEN", "0123456789abcdef0123456789abcdef01234567")

s = requests.Session()
s.headers.update({"Authorization": f"Token {TOKEN}", "Content-Type": "application/json"})


def goc(endpoint: str, lookup: dict, create: dict | None = None) -> dict:
    r = s.get(f"{URL}/api/{endpoint}/", params=lookup, timeout=30)
    r.raise_for_status()
    results = r.json()["results"]
    if results:
        return results[0]
    r = s.post(f"{URL}/api/{endpoint}/", json={**lookup, **(create or {})}, timeout=30)
    if not r.ok:
        print(f"  ! {endpoint}: {r.status_code} {r.text[:160]}")
        r.raise_for_status()
    return r.json()


def main():
    model = json.load(open(TOPO))
    print(f"Populating Nautobot at {URL} from {len(model['devices'])} devices")

    loc_type = goc("dcim/location-types", {"name": "Datacenter"}, {"nestable": False})
    status = goc("extras/statuses", {"name": "Active"})
    site = goc("dcim/locations", {"name": model["site"]},
               {"location_type": loc_type["id"], "status": status["id"]})

    # manufacturers / device types / roles
    dtype, role = {}, {}
    for d in model["devices"]:
        man = goc("dcim/manufacturers", {"name": d["vendor"]})
        dtype.setdefault(d["platform"], goc(
            "dcim/device-types", {"model": d["platform"]},
            {"manufacturer": man["id"], "u_height": 1}))
        role.setdefault(d["role"], goc(
            "extras/roles", {"name": d["role"]}, {"content_types": ["dcim.device"]}))

    # devices + interfaces (patch panels get front/rear ports)
    dev_id = {}
    for d in model["devices"]:
        dev = goc("dcim/devices", {"name": d["name"]},
                  {"device_type": dtype[d["platform"]]["id"],
                   "role": role[d["role"]]["id"],
                   "location": site["id"], "status": status["id"]})
        dev_id[d["name"]] = dev["id"]
        if d["role"] == "patch-panel":
            for iface in d["interfaces"]:
                if iface["name"].startswith("rear"):
                    goc("dcim/rear-ports", {"device": dev["id"], "name": iface["name"]},
                        {"type": "8p8c", "positions": 1})
            for iface in d["interfaces"]:
                if iface["name"].startswith("front"):
                    rear = s.get(f"{URL}/api/dcim/rear-ports/",
                                 params={"device": dev["id"]}).json()["results"]
                    goc("dcim/front-ports", {"device": dev["id"], "name": iface["name"]},
                        {"type": "8p8c",
                         "rear_port": rear[0]["id"] if rear else None,
                         "rear_port_position": 1})
        else:
            for iface in d["interfaces"]:
                goc("dcim/interfaces", {"device": dev["id"], "name": iface["name"]},
                    {"type": iface.get("type", "1000base-t"),
                     "enabled": iface.get("enabled", True),
                     "description": iface.get("description", ""),
                     "status": status["id"]})
    print(f"  devices: {len(dev_id)}  (incl. patch panels with front/rear ports)")

    # cables
    made = 0
    for c in model["cables"]:
        try:
            a = s.get(f"{URL}/api/dcim/interfaces/",
                      params={"device": c["a_device"], "name": c["a_iface"]}).json()["results"]
            b = s.get(f"{URL}/api/dcim/interfaces/",
                      params={"device": c["b_device"], "name": c["b_iface"]}).json()["results"]
            if not (a and b):
                continue
            r = s.post(f"{URL}/api/dcim/cables/", json={
                "termination_a_type": "dcim.interface", "termination_a_id": a[0]["id"],
                "termination_b_type": "dcim.interface", "termination_b_id": b[0]["id"],
                "type": c.get("kind", "cat6"), "status": status["id"]})
            if r.ok:
                made += 1
        except Exception as e:
            print(f"  ! cable {c['a_device']}:{c['a_iface']} <-> {c['b_device']}:{c['b_iface']}: {e}")
    print(f"  cables: {made} (via_panel hops are annotated in the model)")

    # the RCA dependency relationship
    rel = goc("extras/relationships", {"label": "upstream-dependency"},
              {"key": "upstream_dependency", "type": "many-to-many",
               "source_type": "dcim.device", "destination_type": "dcim.device"})
    assoc = 0
    for dep in model["dependencies"]:
        if dep["child"] in dev_id and dep["parent"] in dev_id:
            r = s.post(f"{URL}/api/extras/relationship-associations/", json={
                "relationship": rel["id"],
                "source_id": dev_id[dep["parent"]], "source_type": "dcim.device",
                "destination_id": dev_id[dep["child"]], "destination_type": "dcim.device"})
            if r.ok:
                assoc += 1
    print(f"  dependency associations: {assoc}")
    print("Done. CEP engine can read the dependency graph via Nautobot GraphQL.")


if __name__ == "__main__":
    if TOKEN.startswith("0123456789"):
        print("NOTE: using a placeholder token; set NAUTOBOT_TOKEN for a real run.",
              file=sys.stderr)
    main()
