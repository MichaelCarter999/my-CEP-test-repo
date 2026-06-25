#!/usr/bin/env python3
"""
emit_containerlab.py — derive a runnable containerlab topology from topology.json.

Produces cep-demo.clab.yml with one FRR container per L3/L2 device (patch panels
are passive and omitted from clab, but kept in Nautobot). Links are taken straight
from the canonical cable list so clab, Nautobot and Zabbix never drift.

    sudo containerlab deploy -t cep-demo.clab.yml
    sudo containerlab destroy -t cep-demo.clab.yml

Killing a node for a demo:
    docker stop clab-cep-demo-spur-c1      # cascades down the spur
    docker stop clab-cep-demo-dist03       # black-holes ring C
    docker stop clab-cep-demo-acc-a3       # ring reconverges (no cascade)
"""

#!/usr/bin/env python3
"""
emit_containerlab.py — derive a runnable containerlab topology from topology.json.
"""

import json
import os
from collections import defaultdict

LAB_NAME = "cep-demo"
FRR_IMAGE = "quay.io/frrouting/frr:10.5.0-with-ssh-snmp-zbx-softflowd-iperf3-lldp"
MGMT_NETWORK = "digital-twin"


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    model = json.load(open(os.path.join(here, "topology.json")))

    # -------------------------
    # Build nodes
    # -------------------------
    nodes = {}

    for d in model["devices"]:
        if d["layer"] == "passive":
            continue  # skip patch panels

        nodes[d["name"]] = {
            "kind": "linux",
            "image": FRR_IMAGE,
            "labels": {
                "role": d["role"],
                "layer": d["layer"],
                "protected": str(d["protected"]).lower(),
            },
        }

    # -------------------------
    # Build links (FINAL FIX)
    # -------------------------
    links = []
    iface_counter = defaultdict(int)

    for c in model["cables"]:
        # Skip passive panel hops
        if c["via_panel"]:
            continue

        if is_passive(model, c["a_device"]) or is_passive(model, c["b_device"]):
            continue

        a = c["a_device"]
        b = c["b_device"]

        # Allocate interfaces in EXACT creation order
        iface_counter[a] += 1
        iface_counter[b] += 1

        links.append({
            "endpoints": [
                f"{a}:eth{iface_counter[a]}",
                f"{b}:eth{iface_counter[b]}",
            ]
        })

    # -------------------------
    # Output YAML
    # -------------------------
    clab = {
        "name": LAB_NAME,
        "mgmt": {"network": MGMT_NETWORK},
        "topology": {
            "nodes": nodes,
            "links": links,
        },
    }

    import yaml
    out = os.path.join(here, f"{LAB_NAME}.clab.yml")

    with open(out, "w") as f:
        yaml.safe_dump(clab, f, sort_keys=False)

    print(f"Wrote {out}: {len(nodes)} nodes, {len(links)} links")


def is_passive(model, name):
    for d in model["devices"]:
        if d["name"] == name:
            return d["layer"] == "passive"
    return False


if __name__ == "__main__":
    main()
