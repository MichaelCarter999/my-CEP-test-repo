#!/usr/bin/env python3
"""
send_trap.py — emit a real SNMPv2c trap from the registry.

    python send_trap.py linkDown   --device acc-a1 --ifindex 2
    python send_trap.py coldStart  --device dist01
    python send_trap.py vendorAlarmRaise --device spur-a1     # placeholder until MIB
    python send_trap.py --list

Targets a trap receiver (default 127.0.0.1:1162 — our trapd.py; use :162 for a
real snmptrapd/Zabbix, which needs root). Pure-Python SNMPv2c via snmp_ber, no
pysnmp/net-snmp dependency.
"""
from __future__ import annotations

import argparse
import os
import random
import socket
import sys
import time

import yaml

import snmp_ber as B

HERE = os.path.dirname(os.path.abspath(__file__))
REG = yaml.safe_load(open(os.path.join(HERE, "traps.yaml")))

SYSUPTIME_OID = "1.3.6.1.2.1.1.3.0"
SNMPTRAPOID_OID = "1.3.6.1.6.3.1.1.4.1.0"
SYSNAME_OID = "1.3.6.1.2.1.1.5.0"
SNMPTRAPENTERPRISE_OID = "1.3.6.1.6.3.1.1.4.3.0"

ENC = {
    "Integer": lambda v: B.enc_int(int(v)),
    "OctetString": B.enc_octets,
    "OID": B.enc_oid,
    "TimeTicks": lambda v: B.enc_timeticks(int(v)),
    "IpAddress": B.enc_ipaddress,
    "Counter32": lambda v: B.enc_counter32(int(v)),
    "Gauge32": lambda v: B.enc_gauge32(int(v)),
}


def find_trap(name):
    if name in REG.get("standard", {}):
        return REG["standard"][name], False
    if name in REG.get("enterprise", {}).get("traps", {}):
        return REG["enterprise"]["traps"][name], True
    return None, False


def varbind(oid: str, enc_value: bytes) -> bytes:
    return B.enc_sequence(B.enc_oid(oid), enc_value)


def build_trap(name, device, ifindex, uptime_cs, community="public"):
    spec, is_enterprise = find_trap(name)
    if spec is None:
        raise SystemExit(f"unknown trap '{name}' (use --list)")
    subs = {"device": device, "ifindex": str(ifindex), "index": str(ifindex)}

    vbs = [
        varbind(SYSUPTIME_OID, B.enc_timeticks(uptime_cs)),
        varbind(SNMPTRAPOID_OID, B.enc_oid(spec["oid"])),
        varbind(SYSNAME_OID, B.enc_octets(device)),   # lets the receiver ID the device
    ]
    for vb in spec.get("varbinds", []) or []:
        oid = vb["oid"].format(**subs)
        raw = str(vb["value"]).format(**subs)
        vbs.append(varbind(oid, ENC[vb["type"]](raw)))
    if is_enterprise and REG["enterprise"].get("send_trap_enterprise_varbind"):
        vbs.append(varbind(SNMPTRAPENTERPRISE_OID,
                           B.enc_oid(REG["enterprise"]["enterprise_oid"])))

    pdu_body = (B.enc_int(random.randint(1, 2 ** 31 - 1))   # request-id
                + B.enc_int(0)                               # error-status
                + B.enc_int(0)                               # error-index
                + B.enc_sequence(*vbs))                      # variable-bindings
    pdu = bytes([B.T_TRAP_V2]) + B.enc_len(len(pdu_body)) + pdu_body
    return B.enc_sequence(B.enc_int(1), B.enc_octets(community), pdu)  # v2c=1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("trap", nargs="?", help="trap name (see --list)")
    ap.add_argument("--device", default="acc-a1")
    ap.add_argument("--ifindex", type=int, default=1)
    ap.add_argument("--target", default="127.0.0.1:1162")
    ap.add_argument("--community", default="public")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    if args.list or not args.trap:
        print("standard:  ", ", ".join(REG["standard"]))
        print("enterprise:", ", ".join(REG["enterprise"]["traps"]),
              f"(vendor: {REG['enterprise']['vendor']})")
        return

    host, _, port = args.target.partition(":")
    pkt = build_trap(args.trap, args.device, args.ifindex,
                     int(time.time()) % (2**31), args.community)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.sendto(pkt, (host, int(port or 162)))
    spec, _ = find_trap(args.trap)
    print(f"sent {args.trap} ({spec['oid']}) for {args.device} "
          f"-> {args.target}  [{len(pkt)} bytes, cep_kind={spec['cep_kind']}]")


if __name__ == "__main__":
    main()
