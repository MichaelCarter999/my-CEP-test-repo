# Trap simulator (`trapsim/`)

Sends real SNMPv2c traps for the demo devices — standard MIB-II / IF-MIB traps
fully implemented now, with the **vendor (Actelis) section parameterised** so the
real ML-540 traps drop in as data once you supply the MIB.

Pure Python (no pysnmp / net-snmp): a small BER codec (`snmp_ber.py`) builds and
parses the PDUs, so there's no library-version churn and it runs anywhere.

```
send_trap.py ──SNMPv2c/UDP──▶  [ trapd.py | snmptrapd ]  ──▶ sidecar /events ──▶ correlation
   registry: traps.yaml            path B    path A
```

## Two integration paths

**Path B — direct (fast, self-contained demo):** `trapd.py` receives traps,
maps the trap OID → `cep_kind` (from `traps.yaml`), identifies the device
(sysName varbind, else source-IP → device via `topology.json`), and POSTs to the
sidecar. No Zabbix needed.

**Path A — production:** real Zabbix `snmptrapd` / SNMP-trap items receive the
traps; the existing webhook media type forwards the resulting problems to the
sidecar. Fully built in **`zabbix-path/`** — the official `zabbix-snmptraps`
compose overlay, `snmptrapd.conf`, and `add_trap_items.py` (creates the
`snmptrap[<oid>]` items + `cep_kind`-tagged triggers from this same registry).
See `zabbix-path/README.md`. Same `send_trap.py` drives it — just target `:162`.

## Run it (path B)

```bash
# 1. sidecar up (uses the main topology.json)
cd sidecar && TOPOLOGY_FILE=../topology/topology.json uvicorn app:app --port 8080 &

# 2. trap receiver (1162 = unprivileged; use 162 with sudo for real agents/Zabbix)
python trapsim/trapd.py --port 1162 &

# 3. fire traps
python trapsim/send_trap.py linkDown  --device acc-a1 --ifindex 2 --target 127.0.0.1:1162
python trapsim/send_trap.py linkUp    --device acc-a1 --ifindex 2 --target 127.0.0.1:1162
python trapsim/send_trap.py coldStart --device dist01            --target 127.0.0.1:1162
python trapsim/send_trap.py --list
```

A burst of `linkDown`/`linkUp` on one interface exercises the engine's flap
dampener (collapses to a single FLAPPING alarm). `coldStart`/`warmStart` map to
`RESTART`. Standard traps are realistic device-reported events.

> Reality check: a fully-dead device sends **no** trap (it can't). Device death is
> detected by polling — that's what `faultlab/monitor.py` does. The trap sim and
> the poller are complementary: traps = events a live device reports, polling =
> death detection. Together they mirror a real NOC's two input streams.

## Standard traps implemented (verified)

| name | trap OID | cep_kind | varbinds |
|---|---|---|---|
| coldStart | 1.3.6.1.6.3.1.1.5.1 | RESTART | — |
| warmStart | 1.3.6.1.6.3.1.1.5.2 | RESTART | — |
| linkDown | 1.3.6.1.6.3.1.1.5.3 | LINK_DOWN | ifIndex, ifAdminStatus, ifOperStatus |
| linkUp | 1.3.6.1.6.3.1.1.5.4 | LINK_UP | ifIndex, ifAdminStatus, ifOperStatus |
| authenticationFailure | 1.3.6.1.6.3.1.1.5.5 | SECURITY | — |

Every trap carries the mandatory SNMPv2 pair first — `sysUpTime.0` (TimeTicks)
and `snmpTrapOID.0` (the trap OID) — plus `sysName.0` so the receiver can name
the device. (RFC note: the trap *definitions* are RFC 1157/1215 → SNMPv2-MIB
RFC 3418 / IF-MIB RFC 2863; the varbind *objects* like ifIndex are MIB-II,
RFC 1213. RFC 1213 does not define the traps themselves.)

## Adding the Actelis ML-540 traps (when you have the MIB)

Everything vendor-specific lives in the `enterprise:` block of `traps.yaml`,
currently a clearly-marked **placeholder** (`enterprise_oid: 1.3.6.1.4.1.99999`).
To make it real:

1. Set `enterprise_oid` to Actelis's IANA PEN root (from the MIB / IANA).
2. For each `NOTIFICATION-TYPE` / `TRAP-TYPE` in the Actelis MIB, add an entry:
   its trap OID, a `cep_kind`, and its `OBJECTS`/varbinds (OID, type, value).
3. Map each `cep_kind` to engine behaviour if needed (e.g. a clear trap →
   `CLEAR`). No code change — `send_trap.py` and `trapd.py` read the registry.

Nothing in the codec or the send/receive path is vendor-specific, so this is a
pure-data change. Tests in `tests/test_trapsim.py` cover the codec and the
standard + placeholder-enterprise paths.
