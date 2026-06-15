"""Trap simulator: BER codec + full trap build/parse/classify (no network needed)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "trapsim"))

import snmp_ber as B          # noqa: E402
import send_trap as S         # noqa: E402
import trapd as T             # noqa: E402


def test_ber_oid_and_roundtrip():
    # hand-verified OID encodings
    assert B.enc_oid("1.3.6.1.2.1.1.3.0") == bytes.fromhex("06082b06010201010300")
    assert B.enc_oid("1.3.6.1.4.1.8072").endswith(bytes([0xBF, 0x08]))  # arc >= 128
    # round-trip primitives
    assert B.decode(B.enc_int(255))[1] == 255
    assert B.decode(B.enc_int(0))[1] == 0
    assert B.decode(B.enc_octets("acc-a1"))[1] == "acc-a1"
    assert B.decode(B.enc_ipaddress("10.0.0.11"))[1] == "10.0.0.11"
    assert B.decode(B.enc_timeticks(12345))[1] == 12345


def test_standard_trap_build_parse_classify():
    pkt = S.build_trap("linkDown", "acc-a1", 2, 99999, "public")
    comm, vbs = T.parse_trap(pkt)
    assert comm == "public"
    assert vbs[T.SNMPTRAPOID_OID] == "1.3.6.1.6.3.1.1.5.3"   # IF-MIB linkDown
    assert vbs[T.SYSNAME_OID] == "acc-a1"
    assert vbs["1.3.6.1.2.1.2.2.1.8.2"] == 2                 # ifOperStatus.2 = down
    dev, name, kind, _ = T.classify(vbs, {}, "10.0.0.21")
    assert (dev, name, kind) == ("acc-a1", "linkDown", "LINK_DOWN")


def test_enterprise_placeholder_trap():
    pkt = S.build_trap("vendorAlarmRaise", "spur-a1", 1, 1234, "public")
    _, vbs = T.parse_trap(pkt)
    dev, _name, kind, oid = T.classify(vbs, {}, "10.0.0.31")
    assert (dev, kind) == ("spur-a1", "VENDOR_ALARM")
    assert "1.3.6.1.6.3.1.1.4.3.0" in vbs                    # snmpTrapEnterprise.0


def test_source_ip_fallback():
    vbs = {T.SNMPTRAPOID_OID: "1.3.6.1.6.3.1.1.5.3"}          # no sysName varbind
    dev, *_ = T.classify(vbs, {"10.0.0.24": "acc-a4"}, "10.0.0.24")
    assert dev == "acc-a4"
