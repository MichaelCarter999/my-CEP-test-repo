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
import json
import os

LAB_NAME = "cep-demo"
FRR_IMAGE = "quay.io/frrouting/frr:10.5.0-with-ssh-snmp-zbx-softflowd-iperf3-lldp"
MGMT_NETWORK = "digital-twin"


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    model = json.load(open(os.path.join(here, "topology.json")))

    nodes = {}
    for d in model["devices"]:
        if d["layer"] == "passive":
            continue  # patch panels are passive
        nodes[d["name"]] = {
            "kind": "linux",
            "image": FRR_IMAGE,
            "labels": {
                "role": d["role"],
                "layer": d["layer"],
                "protected": str(d["protected"]).lower(),
            },
        }

    links = []
    for c in model["cables"]:
        # skip the passive panel hop; clab links are device-to-device
        if c["via_panel"]:
            continue
        if model_layer(model, c["a_device"]) == "passive" or \
           model_layer(model, c["b_device"]) == "passive":
            continue
        links.append({"endpoints": [f'{c["a_device"]}:{c["a_iface"]}',
                                     f'{c["b_device"]}:{c["b_iface"]}']})

    clab = {
        "name": LAB_NAME,
        "mgmt": {"network": MGMT_NETWORK},
        "topology": {"nodes": nodes, "links": links},
    }

    import yaml
    out = os.path.join(here, f"{LAB_NAME}.clab.yml")
    with open(out, "w") as f:
        yaml.safe_dump(clab, f, sort_keys=False)
    print(f"Wrote {out}: {len(nodes)} nodes, {len(links)} links")


def model_layer(model, name):
    for d in model["devices"]:
        if d["name"] == name:
            return d["layer"]
    return None


if __name__ == "__main__":
    main()
