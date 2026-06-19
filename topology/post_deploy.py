#!/usr/bin/env python3
"""
post_deploy.py — discover clab container IPs on digital-twin, then seed Nautobot + Zabbix.

Run once after `sudo containerlab deploy -t topology/cep-demo.clab.yml`:

    export NAUTOBOT_TOKEN=0123456789abcdef0123456789abcdef01234567
    export ZBX_TOKEN=<Zabbix UI > Administration > Users > API tokens>
    python topology/post_deploy.py

Writes topology/runtime-ips.json (gitignored) with the real IPs assigned by Docker on
the digital-twin network, then populates Nautobot and Zabbix using those IPs in place
of the placeholder 10.0.0.x values in topology.json.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RUNTIME_IPS = os.path.join(HERE, "runtime-ips.json")
NETWORK = "digital-twin"
LAB_PREFIX = "clab-cep-demo-"


def discover_ips() -> dict[str, str]:
    result = subprocess.run(
        ["docker", "ps", "--filter", f"name={LAB_PREFIX}", "--format", "{{.Names}}"],
        capture_output=True, text=True, check=True,
    )
    containers = [n.strip() for n in result.stdout.splitlines() if n.strip()]
    if not containers:
        sys.exit(f"No containers matching '{LAB_PREFIX}*' found — is the lab deployed?")

    ips: dict[str, str] = {}
    for cname in containers:
        data = json.loads(subprocess.run(
            ["docker", "inspect", cname],
            capture_output=True, text=True, check=True,
        ).stdout)[0]
        networks = data["NetworkSettings"]["Networks"]
        if NETWORK not in networks:
            print(f"  warn: {cname} not on {NETWORK}, skipping")
            continue
        ip = networks[NETWORK]["IPAddress"]
        device = cname[len(LAB_PREFIX):]  # strip "clab-cep-demo-" prefix
        ips[device] = ip
        print(f"  {device:20s} {ip}")

    return ips


def main():
    print(f"Discovering container IPs on '{NETWORK}'...")
    ips = discover_ips()
    print(f"Found {len(ips)} nodes.\n")

    with open(RUNTIME_IPS, "w") as f:
        json.dump(ips, f, indent=2)
    print(f"Wrote {RUNTIME_IPS}\n")

    os.environ["CEP_TOPO_IPS"] = RUNTIME_IPS
    sys.path.insert(0, ROOT)

    print("=== Seeding Nautobot ===")
    try:
        import nautobot.populate_nautobot as pnb
        pnb.main()
    except Exception as e:
        print(f"Nautobot seed failed: {e}", file=sys.stderr)

    print("\n=== Seeding Zabbix ===")
    try:
        import zabbix.populate_zabbix as pzb
        pzb.main()
    except Exception as e:
        print(f"Zabbix seed failed: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
