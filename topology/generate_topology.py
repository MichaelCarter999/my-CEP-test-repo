#!/usr/bin/env python3
"""
generate_topology.py — single source of truth for the CEP demo network.

Defines a ~32-node FRR-based network and emits a normalised model that every
downstream consumer reads:

    topology.json   canonical model (devices, interfaces, cables, panels, deps)
    topology.yaml   human-readable mirror

Network design (deliberately chosen to exercise correlation semantics):

    core01 ── core02            dual L3 core (OSPF, redundant)
       │        │
    dist01   dist02   dist03    L3 distribution, one per access ring
       │        │        │
    [Ring A] [Ring B] [Ring C]  L2 access rings, RSTP ring protection (6 each)
       │                 │
    spur-a*           spur-c*   unprotected chains hanging off ring members

Why this shape matters for CEP:
  * Spurs are UNPROTECTED chains: a spur-head failure cascades cleanly to every
    node below it -> textbook root-cause suppression.
  * Rings are PROTECTED by RSTP: losing ONE ring switch does NOT isolate its
    peers (the ring reconverges), so peer alarms must NOT be suppressed.
    But losing the ring's distribution uplink DOES black-hole the whole ring.
  * The dual core is redundant: a single core loss is survivable.

That gives the correlator three distinct, demonstrable behaviours instead of
one naive "parent down => mute everything", which is the whole argument for
deterministic, topology-aware correlation.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Optional

import yaml

SITE = "demo-dc1"
MGMT_PREFIX = "10.0.0"          # mgmt /24 for SNMP + agent
LOOPBACK_PREFIX = "10.255"      # router-id / loopbacks


@dataclass
class Interface:
    name: str
    enabled: bool = True
    type: str = "1000base-t"
    description: str = ""


@dataclass
class Device:
    name: str
    role: str                    # core | distribution | access | spur | patch-panel
    layer: str                   # L3 | L2 | passive
    vendor: str = "FRR"
    platform: str = "frr-9"
    site: str = SITE
    mgmt_ip: Optional[str] = None
    monitoring: list[str] = field(default_factory=list)  # ["agent","snmp"]
    protected: bool = False       # part of an RSTP ring?
    interfaces: list[Interface] = field(default_factory=list)


@dataclass
class Cable:
    a_device: str
    a_iface: str
    b_device: str
    b_iface: str
    kind: str = "trunk"          # trunk | uplink | ring | spur | core
    via_panel: Optional[str] = None


@dataclass
class Dependency:
    """A directed 'child depends on parent for reachability' edge for the CEP graph."""
    child: str
    parent: str
    relation: str                # uplink | ring-gateway | spur-chain | core-mesh
    protected: bool = False      # is this dependency protected (redundant/RSTP)?


class TopologyBuilder:
    def __init__(self) -> None:
        self.devices: dict[str, Device] = {}
        self.cables: list[Cable] = []
        self.deps: list[Dependency] = []
        self._mgmt_octet = 10

    # ---- helpers -----------------------------------------------------------
    def _next_mgmt(self) -> str:
        ip = f"{MGMT_PREFIX}.{self._mgmt_octet}"
        self._mgmt_octet += 1
        return ip

    def add_device(self, name, role, layer, monitoring, protected=False,
                   vendor="FRR", platform="frr-9", mgmt=True) -> Device:
        d = Device(
            name=name, role=role, layer=layer, vendor=vendor, platform=platform,
            monitoring=monitoring, protected=protected,
            mgmt_ip=self._next_mgmt() if mgmt else None,
        )
        self.devices[name] = d
        return d

    def _iface(self, dev: Device, name: str, desc: str = "") -> str:
        if not any(i.name == name for i in dev.interfaces):
            dev.interfaces.append(Interface(name=name, description=desc))
        return name

    def link(self, a, ai, b, bi, kind="trunk", via_panel=None):
        self._iface(self.devices[a], ai, f"to {b}")
        self._iface(self.devices[b], bi, f"to {a}")
        if via_panel:
            self._iface(self.devices[via_panel], f"front-{a}", "patch front")
            self._iface(self.devices[via_panel], f"rear-{b}", "patch rear")
        self.cables.append(Cable(a, ai, b, bi, kind, via_panel))

    def depend(self, child, parent, relation, protected=False):
        self.deps.append(Dependency(child, parent, relation, protected))

    # ---- network construction ---------------------------------------------
    def build(self):
        # Core (dual, redundant L3)
        for c in ("core01", "core02"):
            self.add_device(c, "core", "L3", ["agent", "snmp"])
        self.link("core01", "eth1", "core02", "eth1", kind="core")
        # cores depend on each other but the dependency is PROTECTED (redundant)
        self.depend("core01", "core02", "core-mesh", protected=True)
        self.depend("core02", "core01", "core-mesh", protected=True)

        # Distribution (one per ring), dual-homed to both cores
        dists = ["dist01", "dist02", "dist03"]
        for i, d in enumerate(dists, start=1):
            self.add_device(d, "distribution", "L3", ["agent", "snmp"])
            self.link(d, "eth1", "core01", f"eth{1+i}", kind="uplink")
            self.link(d, "eth2", "core02", f"eth{1+i}", kind="uplink")
            # protected: dual-homed to two cores
            self.depend(d, "core01", "uplink", protected=True)
            self.depend(d, "core02", "uplink", protected=True)

        # Patch panels on the dist->ring runs (passive, modelled in Nautobot)
        panels = ["pp-a", "pp-b", "pp-c"]
        for p in panels:
            self.add_device(p, "patch-panel", "passive", [], mgmt=False,
                            vendor="generic", platform="passive-24")

        # Access rings (RSTP-protected L2), 6 switches each, closed ring
        rings = {"a": ("dist01", "pp-a"), "b": ("dist02", "pp-b"), "c": ("dist03", "pp-c")}
        ring_members: dict[str, list[str]] = {}
        for ring, (dist, panel) in rings.items():
            members = [f"acc-{ring}{n}" for n in range(1, 7)]
            ring_members[ring] = members
            for m in members:
                self.add_device(m, "access", "L2", ["snmp"], protected=True)
                # every ring member's gateway is the dist uplink (UNPROTECTED:
                # lose the dist and the whole ring is black-holed)
                self.depend(m, dist, "ring-gateway", protected=False)
            # uplink: first ring member to dist via patch panel
            self.link(members[0], "eth1", dist, f"eth{3}", kind="uplink", via_panel=panel)
            # close the ring: chain members then link last->first (RSTP blocks one port)
            for i in range(len(members)):
                a = members[i]
                b = members[(i + 1) % len(members)]
                self.link(a, "eth2" if i else "eth2", b, "eth3", kind="ring")
            # NOTE: ring peers are NOT dependencies of each other (RSTP protects)

        # Spurs (UNPROTECTED chains) hanging off specific ring members
        spurs = {
            "acc-a4": ["spur-a1", "spur-a2", "spur-a3"],     # long spur
            "acc-b3": ["spur-b1", "spur-b2"],                # short spur
            "acc-c5": ["spur-c1", "spur-c2", "spur-c3", "spur-c4"],  # long spur
        }
        for head, chain in spurs.items():
            prev = head
            for node in chain:
                self.add_device(node, "spur", "L2", ["snmp"], protected=False)
                self.link(prev, "eth4", node, "eth1", kind="spur")
                # UNPROTECTED chain dependency: each node depends on the one above
                self.depend(node, prev, "spur-chain", protected=False)
                prev = node

        return self

    # ---- export ------------------------------------------------------------
    def model(self) -> dict:
        return {
            "site": SITE,
            "summary": {
                "device_count": len(self.devices),
                "cable_count": len(self.cables),
                "dependency_count": len(self.deps),
                "rings": 3,
                "spurs": 3,
            },
            "devices": [asdict(d) for d in self.devices.values()],
            "cables": [asdict(c) for c in self.cables],
            "dependencies": [asdict(d) for d in self.deps],
        }


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    model = TopologyBuilder().build().model()

    with open(os.path.join(here, "topology.json"), "w") as f:
        json.dump(model, f, indent=2)
    with open(os.path.join(here, "topology.yaml"), "w") as f:
        yaml.safe_dump(model, f, sort_keys=False, default_flow_style=False)

    s = model["summary"]
    print(f"Generated topology for site '{model['site']}'")
    print(f"  devices:      {s['device_count']}")
    print(f"  cables:       {s['cable_count']}")
    print(f"  dependencies: {s['dependency_count']}")
    print(f"  rings:        {s['rings']} (RSTP-protected)")
    print(f"  spurs:        {s['spurs']} (unprotected chains)")
    print("  wrote topology.json + topology.yaml")


if __name__ == "__main__":
    main()
