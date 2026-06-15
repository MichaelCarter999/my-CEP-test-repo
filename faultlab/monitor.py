#!/usr/bin/env python3
"""
monitor.py — detection agent for the FRR thin slice.

Polls each monitored device and emits exactly what a NOC monitoring system would:
  - container stopped (the device itself is down)          -> NODE_DOWN
  - container up but its loopback unreachable over the      -> UNREACHABLE
    OSPF data plane (cut off by an upstream failure)
  - recovered                                               -> CLEAR
and POSTs state changes to the CEP sidecar /events. The sidecar's reachability
correlation then decides root cause vs symptom.

This is the stand-in for Zabbix in the thin slice: it does exactly what a Zabbix
"ICMP unreachable" + "Zabbix agent not available" trigger pair would, so once you
point real Zabbix at these hosts the webhook replaces this script unchanged.

Real run:   python monitor.py
Dry/logic:  python monitor.py --mock faultlab/state.example.json --once
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import urllib.request

SIDECAR = os.environ.get("SIDECAR_URL", "http://localhost:8080")
LAB = "clab-cep-faultlab"
# device -> loopback (kept in sync with generate_faultlab.py NODES)
DEVICES = {
    "core01": "10.255.0.1", "core02": "10.255.0.2", "dist01": "10.255.0.11",
    "acc-a1": "10.255.0.21", "acc-a4": "10.255.0.24",
    "spur-a1": "10.255.0.31", "spur-a2": "10.255.0.32", "spur-a3": "10.255.0.33",
}


# ---- probes (real docker) --------------------------------------------------
def container_running(node: str) -> bool:
    r = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", f"{LAB}-{node}"],
        capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip() == "true"


def data_plane_reachable(loopback: str) -> bool:
    r = subprocess.run(
        ["docker", "exec", f"{LAB}-probe", "ping", "-c", "1", "-W", "1", loopback],
        capture_output=True, text=True)
    return r.returncode == 0


# ---- probes (mock) ---------------------------------------------------------
class MockProbe:
    """state file: {"stopped": ["spur-a1"], "unreachable_lo": ["10.255.0.32"]}"""
    def __init__(self, path):
        self.state = json.load(open(path))

    def running(self, node):
        return node not in self.state.get("stopped", [])

    def reachable(self, lo):
        return lo not in self.state.get("unreachable_lo", [])


# ---- classification + emit -------------------------------------------------
def classify(node, lo, running_fn, reach_fn) -> str:
    if not running_fn(node):
        return "NODE_DOWN"
    return "HEALTHY" if reach_fn(lo) else "UNREACHABLE"


def post(event: dict):
    data = json.dumps(event).encode()
    req = urllib.request.Request(f"{SIDECAR}/events", data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5):
            return True
    except Exception as e:
        print(f"  ! sidecar post failed: {e}")
        return False


def poll_once(running_fn, reach_fn, prev: dict, verbose=True) -> dict:
    now = time.time()
    new = {}
    for node, lo in DEVICES.items():
        state = classify(node, lo, running_fn, reach_fn)
        new[node] = state
        if state == prev.get(node):
            continue  # no change
        if state == "NODE_DOWN":
            post({"device": node, "kind": "NODE_DOWN", "source": "monitor", "ts": now})
        elif state == "UNREACHABLE":
            post({"device": node, "kind": "UNREACHABLE", "source": "monitor", "ts": now})
        elif state == "HEALTHY" and prev.get(node) in ("NODE_DOWN", "UNREACHABLE"):
            post({"device": node, "kind": "CLEAR", "source": "monitor", "ts": now})
        if verbose:
            print(f"  {node:8} {prev.get(node, '-'):11} -> {state}")
    return new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=3.0)
    ap.add_argument("--mock", help="path to a mock state JSON file")
    ap.add_argument("--once", action="store_true", help="single poll then exit")
    args = ap.parse_args()

    if args.mock:
        m = MockProbe(args.mock)
        running_fn, reach_fn = m.running, m.reachable
    else:
        running_fn, reach_fn = container_running, data_plane_reachable

    prev = {}
    print(f"monitoring {len(DEVICES)} devices -> {SIDECAR}")
    while True:
        prev = poll_once(running_fn, reach_fn, prev)
        if args.once:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
