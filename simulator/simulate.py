#!/usr/bin/env python3
"""
simulate.py — drive deterministic fault scenarios against the CEP sidecar.

Reads topology.json so scenarios reference real devices, then posts alarm events
to the sidecar (and optionally Zabbix via zabbix_sender). Each scenario is built
to demonstrate a distinct correlation behaviour.

Usage:
    python simulate.py --scenario spur_cascade
    python simulate.py --scenario list
    python simulate.py --scenario storm --rate 200      # scale/perf test
"""
from __future__ import annotations

import argparse
import json
import os
import random
import time
import urllib.request

SIDECAR = os.environ.get("SIDECAR_URL", "http://localhost:8100")
HERE = os.path.dirname(os.path.abspath(__file__))
TOPO = os.environ.get("TOPOLOGY_FILE",
                      os.path.join(HERE, "..", "topology", "topology.json"))


def load_model():
    with open(TOPO) as f:
        return json.load(f)


def post(events: list[dict]):
    data = json.dumps(events).encode()
    req = urllib.request.Request(f"{SIDECAR}/events/batch", data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def clear():
    req = urllib.request.Request(f"{SIDECAR}/clear", data=b"", method="POST")
    urllib.request.urlopen(req, timeout=10)


def children_of(model, parent):
    """Devices that depend (directly or transitively) on `parent`."""
    deps = model["dependencies"]
    direct = {d["child"] for d in deps if d["parent"] == parent}
    out = set(direct)
    frontier = list(direct)
    while frontier:
        p = frontier.pop()
        for d in deps:
            if d["parent"] == p and d["child"] not in out:
                out.add(d["child"])
                frontier.append(d["child"])
    return out


# -- scenarios ---------------------------------------------------------------
def scn_spur_cascade(model):
    """Unprotected spur head fails -> clean downstream cascade."""
    head = "spur-c1"
    kids = children_of(model, head)
    now = time.time()
    evts = [{"device": head, "kind": "NODE_DOWN", "ts": now}]
    evts += [{"device": k, "kind": "UNREACHABLE", "ts": now + random.uniform(0.1, 2)}
             for k in kids]
    return evts, f"{head} (spur head) down -> {len(kids)} downstream nodes"


def scn_ring_protected(model):
    """One RSTP ring member fails -> peers must NOT be suppressed."""
    target = "acc-a3"
    peers = ["acc-a2", "acc-a4", "acc-a5"]
    now = time.time()
    evts = [{"device": target, "kind": "NODE_DOWN", "ts": now}]
    evts += [{"device": p, "kind": "UNREACHABLE", "ts": now + 0.3} for p in peers]
    return evts, f"{target} (ring member) down -> peers stay independent (RSTP)"


def scn_dist_blackhole(model):
    """Distribution (ring gateway) fails -> entire ring + spurs black-holed."""
    dist = "dist03"
    kids = children_of(model, dist)
    now = time.time()
    evts = [{"device": dist, "kind": "NODE_DOWN", "ts": now}]
    evts += [{"device": k, "kind": "UNREACHABLE", "ts": now + random.uniform(0.1, 3)}
             for k in kids]
    return evts, f"{dist} down -> ring C + spurs ({len(kids)} nodes) black-holed"


def scn_core_redundant(model):
    """Single core fails -> redundancy means nothing downstream is lost."""
    now = time.time()
    evts = [{"device": "core01", "kind": "NODE_DOWN", "ts": now}]
    evts += [{"device": d, "kind": "UNREACHABLE", "ts": now + 0.2}
             for d in ("dist01", "dist02")]
    return evts, "core01 down -> survivable via core02 (no suppression)"


def scn_flap(model):
    """Interface flap storm -> dampened to a single FLAPPING alarm."""
    now = time.time()
    evts = [{"device": "acc-b2", "kind": "IF_FLAP", "interface": "eth2",
             "ts": now + i * 0.5} for i in range(8)]
    return evts, "acc-b2 eth2 flapping x8 -> damped to 1 FLAPPING alarm"


def scn_mixed(model):
    """Realistic mix: a dist cascade + independent unrelated noise."""
    evts, _ = scn_dist_blackhole(model)
    now = time.time()
    # independent noise that must survive (different ring, no common cause)
    noise = ["acc-a1", "spur-b1"]
    evts += [{"device": n, "kind": "NODE_DOWN", "ts": now + 1} for n in noise]
    return evts, "dist03 cascade + 2 independent failures (precision test)"


def scn_storm(model, rate):
    """High-volume throughput test: a big cascade fired as fast as possible."""
    dist = "dist01"
    kids = list(children_of(model, dist))
    now = time.time()
    evts = [{"device": dist, "kind": "NODE_DOWN", "ts": now}]
    # amplify by repeating downstream alarms to simulate a noisy real NOC
    reps = max(1, rate // max(1, len(kids)))
    for r in range(reps):
        evts += [{"device": k, "kind": "UNREACHABLE", "ts": now + 0.01 * r}
                 for k in kids]
    return evts, f"storm: {len(evts)} alarms from dist01 cascade"


SCENARIOS = {
    "spur_cascade": scn_spur_cascade,
    "ring_protected": scn_ring_protected,
    "dist_blackhole": scn_dist_blackhole,
    "core_redundant": scn_core_redundant,
    "flap": scn_flap,
    "mixed": scn_mixed,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="list")
    ap.add_argument("--rate", type=int, default=200)
    ap.add_argument("--no-clear", action="store_true")
    args = ap.parse_args()

    if args.scenario == "list":
        print("Scenarios:")
        for k, fn in SCENARIOS.items():
            print(f"  {k:16} {fn.__doc__.strip().splitlines()[0]}")
        print(f"  {'storm':16} High-volume throughput test (--rate N)")
        return

    model = load_model()
    if not args.no_clear:
        clear()

    if args.scenario == "storm":
        evts, desc = scn_storm(model, args.rate)
    else:
        if args.scenario not in SCENARIOS:
            print(f"unknown scenario: {args.scenario}")
            return
        evts, desc = SCENARIOS[args.scenario](model)

    t0 = time.perf_counter()
    res = post(evts)
    dt = (time.perf_counter() - t0) * 1000
    m = res["metrics"]
    print(f"Scenario: {desc}")
    print(f"  posted {len(evts)} alarms in {dt:.0f} ms")
    print(f"  root_causes={m['root_causes']} symptoms={m['symptoms']} "
          f"active={m['active']} flapping={m['flapping']}")
    print(f"  suppression_ratio={m['suppression_ratio']:.0%} "
          f"correlation_latency={m['last_latency_ms']:.2f} ms")


if __name__ == "__main__":
    main()
