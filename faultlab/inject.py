#!/usr/bin/env python3
"""
inject.py — create REAL faults in the FRR thin slice (not simulated events).

    python inject.py stop spur-a1     # kill a spur head -> real OSPF withdrawal
    python inject.py start spur-a1     # bring it back
    python inject.py scenario spur_cascade
    python inject.py heal-all

The monitor.py loop detects the resulting reachability change over the data plane
and feeds the sidecar; correlation happens there. This script only causes faults.
"""
import argparse
import subprocess
import sys

LAB = "clab-cep-faultlab"
DEVICES = ["core01", "core02", "dist01", "acc-a1", "acc-a4",
           "spur-a1", "spur-a2", "spur-a3"]

SCENARIOS = {
    "spur_cascade": ["spur-a1"],      # head down -> a2,a3 cut off (cascade)
    "spur_tip": ["spur-a3"],          # tip down -> no downstream (single alarm)
    "dist_blackhole": ["dist01"],     # ring gateway -> acc-a1, acc-a4, spurs lost
    "core_single": ["core01"],        # redundant -> nothing downstream lost
    "acc_independent": ["acc-a1"],    # sibling leaf -> isolated, not a symptom
}


def docker(action, node):
    cn = f"{LAB}-{node}"
    print(f"  docker {action} {cn}")
    r = subprocess.run(["docker", action, cn], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  ! {r.stderr.strip()}")
    return r.returncode == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["stop", "start", "scenario", "heal-all", "list"])
    ap.add_argument("target", nargs="?")
    args = ap.parse_args()

    if args.cmd == "list":
        print("devices:  ", ", ".join(DEVICES))
        print("scenarios:", ", ".join(SCENARIOS))
    elif args.cmd == "heal-all":
        for n in DEVICES:
            docker("start", n)
    elif args.cmd in ("stop", "start"):
        if not args.target:
            sys.exit(f"usage: inject.py {args.cmd} <device>")
        docker(args.cmd, args.target)
    elif args.cmd == "scenario":
        if args.target not in SCENARIOS:
            sys.exit(f"unknown scenario; choose from {list(SCENARIOS)}")
        for n in SCENARIOS[args.target]:
            docker("stop", n)
        print(f"scenario '{args.target}' applied — watch the monitor + UI")


if __name__ == "__main__":
    main()
