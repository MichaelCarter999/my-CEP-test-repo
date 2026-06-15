#!/usr/bin/env python3
"""
generate_faultlab.py — a minimal, runnable FRR thin slice for real fault injection.

Routed-only (all FRR/OSPF, no L2 rings) so it actually runs on a laptop and the
failures are real, not simulated. It reuses device NAMES from the main topology
(core01, core02, dist01, acc-a4, acc-a1, spur-a1..a3) so the existing CEP sidecar
graph correlates it with zero changes.

Shape (a routed spur off dist01, plus a sibling leaf and a redundant core):

    core01 ═ core02          dual core (OSPF), dist01 dual-homed -> redundancy demo
        ╲   ╱
        dist01
        ╱    ╲
    acc-a1   acc-a4          acc-a1 = independent sibling (survives spur faults)
                 │
              spur-a1 ─ spur-a2 ─ spur-a3   unprotected chain -> cascade demo

Emits:
    faultlab.clab.yml                 containerlab topology (8 FRR + 1 probe)
    configs/<node>/frr.conf           OSPF + interface addressing
    configs/<node>/daemons            enable zebra + ospfd

Then:  sudo containerlab deploy -t faultlab.clab.yml
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
FRR_IMAGE = "quay.io/frrouting/frr:9.1.0"
PROBE_IMAGE = "alpine:3.20"

# node -> loopback id (router-id + advertised /32)
NODES = {
    "core01": "10.255.0.1",
    "core02": "10.255.0.2",
    "dist01": "10.255.0.11",
    "acc-a1": "10.255.0.21",
    "acc-a4": "10.255.0.24",
    "spur-a1": "10.255.0.31",
    "spur-a2": "10.255.0.32",
    "spur-a3": "10.255.0.33",
}

# point-to-point links: (a, a_if, a_ip, b, b_if, b_ip, /30 net)
LINKS = [
    ("core01", "eth1", "10.0.0.1", "core02", "eth1", "10.0.0.2"),     # core mesh
    ("core01", "eth2", "10.0.1.1", "dist01", "eth1", "10.0.1.2"),     # dist uplink A
    ("core02", "eth2", "10.0.2.1", "dist01", "eth2", "10.0.2.2"),     # dist uplink B (redundant)
    ("dist01", "eth3", "10.0.3.1", "acc-a1", "eth1", "10.0.3.2"),     # sibling leaf
    ("dist01", "eth4", "10.0.4.1", "acc-a4", "eth1", "10.0.4.2"),     # spur gateway
    ("acc-a4", "eth2", "10.0.5.1", "spur-a1", "eth1", "10.0.5.2"),    # spur chain
    ("spur-a1", "eth2", "10.0.6.1", "spur-a2", "eth1", "10.0.6.2"),
    ("spur-a2", "eth2", "10.0.7.1", "spur-a3", "eth1", "10.0.7.2"),
]
# probe attaches to core01 so it pings every loopback over the OSPF data plane
PROBE_LINK = ("core01", "eth9", "10.0.9.1", "probe", "eth1", "10.0.9.2")


def node_interfaces(node):
    """Return [(ifname, ip)] for a node across all links."""
    out = []
    for a, aif, aip, b, bif, bip in LINKS:
        if a == node:
            out.append((aif, aip))
        if b == node:
            out.append((bif, bip))
    if node == PROBE_LINK[0]:
        out.append((PROBE_LINK[1], PROBE_LINK[2]))
    return out


def write_frr_configs():
    cfgdir = os.path.join(HERE, "configs")
    for node, lo in NODES.items():
        d = os.path.join(cfgdir, node)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "daemons"), "w") as f:
            f.write("zebra=yes\nospfd=yes\n")
            for x in ("bgpd", "ripd", "ripngd", "ospf6d", "isisd", "pimd",
                      "ldpd", "nhrpd", "eigrpd", "babeld", "sharpd", "staticd",
                      "pbrd", "bfdd", "fabricd", "vrrpd", "pathd"):
                f.write(f"{x}=no\n")
            f.write('vtysh_enable=yes\nzebra_options=" -A 127.0.0.1 -s 90000000"\n'
                    'ospfd_options="  -A 127.0.0.1"\n')

        lines = ["frr defaults traditional", "hostname " + node,
                 "no ipv6 forwarding", "!",
                 "interface lo", f" ip address {lo}/32", " ip ospf area 0", "!"]
        for ifn, ip in node_interfaces(node):
            lines += [f"interface {ifn}", f" ip address {ip}/30",
                      " ip ospf network point-to-point", " ip ospf area 0", "!"]
        lines += ["router ospf", f" ospf router-id {lo}",
                  " redistribute connected", "!", "line vty", "!"]
        with open(os.path.join(d, "frr.conf"), "w") as f:
            f.write("\n".join(lines) + "\n")


def write_clab():
    nodes_yml = []
    for node in NODES:
        nodes_yml.append(f"""    {node}:
      kind: linux
      image: {FRR_IMAGE}
      binds:
        - configs/{node}/frr.conf:/etc/frr/frr.conf
        - configs/{node}/daemons:/etc/frr/daemons""")
    # probe: alpine with a default route via core01 so loopbacks are reachable
    nodes_yml.append(f"""    probe:
      kind: linux
      image: {PROBE_IMAGE}
      exec:
        - ip addr add {PROBE_LINK[5]}/30 dev {PROBE_LINK[4]}
        - ip route replace default via {PROBE_LINK[2]}""")

    links_yml = []
    for a, aif, _, b, bif, _ in LINKS:
        links_yml.append(f'    - endpoints: ["{a}:{aif}", "{b}:{bif}"]')
    links_yml.append(f'    - endpoints: ["{PROBE_LINK[0]}:{PROBE_LINK[1]}", '
                     f'"{PROBE_LINK[3]}:{PROBE_LINK[4]}"]')

    clab = ("name: cep-faultlab\n"
            "topology:\n  nodes:\n" + "\n".join(nodes_yml) +
            "\n  links:\n" + "\n".join(links_yml) + "\n")
    with open(os.path.join(HERE, "faultlab.clab.yml"), "w") as f:
        f.write(clab)


def main():
    write_frr_configs()
    write_clab()
    probes = list(NODES.keys())
    print(f"Wrote faultlab.clab.yml ({len(NODES)} FRR nodes + 1 probe) "
          f"and configs/<node>/{{frr.conf,daemons}}")
    print("monitored devices:", ", ".join(probes))
    print("deploy: sudo containerlab deploy -t faultlab.clab.yml")


if __name__ == "__main__":
    main()
