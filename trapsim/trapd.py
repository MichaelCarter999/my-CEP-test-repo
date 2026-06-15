#!/usr/bin/env python3
"""
trapd.py — minimal SNMPv2c trap receiver that feeds the CEP sidecar.

Decodes incoming traps (via snmp_ber), looks up the trap OID in traps.yaml to get
its cep_kind, identifies the device (sysName.0 varbind, else source-IP -> device
from topology.json mgmt_ip), and POSTs {device, kind} to the sidecar /events.

    sudo python trapd.py                 # listen on :162 (privileged)
    python trapd.py --port 1162          # unprivileged, for local testing

This is PATH B (direct: trap -> sidecar), for a fast self-contained demo.
PATH A (production) replaces this with Zabbix's own snmptrapd/SNMP trap items;
the existing webhook media type then forwards problems to the sidecar. The
OID -> kind mapping here mirrors what you'd configure as Zabbix trap triggers.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import urllib.request

import yaml

import snmp_ber as B

HERE = os.path.dirname(os.path.abspath(__file__))
REG = yaml.safe_load(open(os.path.join(HERE, "traps.yaml")))
SIDECAR = os.environ.get("SIDECAR_URL", "http://localhost:8080")
SNMPTRAPOID_OID = "1.3.6.1.6.3.1.1.4.1.0"
SYSNAME_OID = "1.3.6.1.2.1.1.5.0"

# build OID -> (name, cep_kind) once
OID2KIND = {}
for _n, _s in REG.get("standard", {}).items():
    OID2KIND[_s["oid"]] = (_n, _s["cep_kind"])
for _n, _s in REG.get("enterprise", {}).get("traps", {}).items():
    OID2KIND[_s["oid"]] = (_n, _s["cep_kind"])


def load_ip_map():
    """source IP -> device, from the canonical topology (mgmt_ip)."""
    path = os.path.join(HERE, "..", "topology", "topology.json")
    out = {}
    try:
        model = json.load(open(path))
        for d in model["devices"]:
            if d.get("mgmt_ip"):
                out[d["mgmt_ip"]] = d["name"]
    except Exception:
        pass
    return out


def parse_trap(pkt: bytes):
    """Return (community, {oid: value}) varbinds, or None if not a v2c trap."""
    tag, msg, _ = B.decode(pkt)
    if tag != B.T_SEQUENCE:
        return None
    community = msg[1][1]
    # msg[2] = (T_TRAP_V2, [request-id, error-status, error-index, varbind-list])
    pdu_children = msg[2][1]
    vb_list = pdu_children[3][1]
    vbs = {}
    for _t, pair in vb_list:
        oid = pair[0][1]
        val = pair[1][1]
        vbs[oid] = val
    return community, vbs


def classify(vbs, ip_map, src_ip):
    trap_oid = vbs.get(SNMPTRAPOID_OID)
    name, kind = OID2KIND.get(trap_oid, ("unknown", "UNKNOWN"))
    device = vbs.get(SYSNAME_OID) or ip_map.get(src_ip, src_ip)
    return device, name, kind, trap_oid


def post(device, kind):
    body = json.dumps({"device": device, "kind": kind, "source": "trap"}).encode()
    req = urllib.request.Request(f"{SIDECAR}/events", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5):
            return True
    except Exception as e:
        print(f"  ! sidecar post failed: {e}")
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=162)
    ap.add_argument("--bind", default="0.0.0.0")
    ap.add_argument("--once", action="store_true", help="handle one trap then exit")
    args = ap.parse_args()

    ip_map = load_ip_map()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind((args.bind, args.port))
    print(f"trapd listening on {args.bind}:{args.port} -> {SIDECAR}  "
          f"({len(OID2KIND)} trap OIDs known, {len(ip_map)} device IPs)")
    while True:
        pkt, addr = s.recvfrom(65535)
        try:
            parsed = parse_trap(pkt)
            if not parsed:
                continue
            _community, vbs = parsed
            device, name, kind, oid = classify(vbs, ip_map, addr[0])
            print(f"  trap {name} ({oid}) from {addr[0]} -> device={device} kind={kind}")
            if kind not in ("UNKNOWN", "SECURITY"):
                post(device, kind)
        except Exception as e:
            print(f"  ! parse error from {addr[0]}: {e}")
        if args.once:
            break


if __name__ == "__main__":
    main()
