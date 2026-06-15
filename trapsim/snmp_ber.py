"""
snmp_ber.py — minimal, dependency-free BER (ASN.1) codec for SNMPv2c traps.

Just enough of X.690 to build and parse SNMPv2-Trap PDUs: INTEGER, OCTET STRING,
NULL, OBJECT IDENTIFIER, SEQUENCE, and the SNMP application types TimeTicks,
IpAddress, Counter32, Gauge32. No pysnmp/net-snmp dependency, so it runs anywhere
and there is no library-version churn to manage.

Encoders return bytes; decode() returns a small tagged-value tree. Round-trip and
independently cross-checked in tests/test_trapsim.py.
"""
from __future__ import annotations

# --- tags -------------------------------------------------------------------
T_INTEGER = 0x02
T_OCTETSTRING = 0x04
T_NULL = 0x05
T_OID = 0x06
T_SEQUENCE = 0x30          # constructed
T_IPADDRESS = 0x40         # APPLICATION 0, primitive
T_COUNTER32 = 0x41         # APPLICATION 1
T_GAUGE32 = 0x42           # APPLICATION 2
T_TIMETICKS = 0x43         # APPLICATION 3
T_TRAP_V2 = 0xA7           # context [7] constructed: SNMPv2-Trap-PDU


# --- length -----------------------------------------------------------------
def enc_len(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    out = b""
    while n:
        out = bytes([n & 0xFF]) + out
        n >>= 8
    return bytes([0x80 | len(out)]) + out


def _tlv(tag: int, value: bytes) -> bytes:
    return bytes([tag]) + enc_len(len(value)) + value


# --- primitive encoders -----------------------------------------------------
def enc_int(value: int, tag: int = T_INTEGER) -> bytes:
    if value == 0:
        return _tlv(tag, b"\x00")
    v = value
    out = b""
    if v > 0:
        while v:
            out = bytes([v & 0xFF]) + out
            v >>= 8
        if out[0] & 0x80:                 # keep it positive
            out = b"\x00" + out
    else:                                  # two's complement (rare for SNMP)
        v = (1 << (8 * ((value.bit_length() // 8) + 1))) + value
        while v:
            out = bytes([v & 0xFF]) + out
            v >>= 8
    return _tlv(tag, out)


def enc_octets(value) -> bytes:
    if isinstance(value, str):
        value = value.encode()
    return _tlv(T_OCTETSTRING, value)


def enc_null() -> bytes:
    return _tlv(T_NULL, b"")


def enc_oid(oid: str) -> bytes:
    parts = [int(x) for x in oid.strip(".").split(".")]
    if len(parts) < 2:
        raise ValueError("OID needs >= 2 arcs")
    body = bytes([40 * parts[0] + parts[1]])
    for arc in parts[2:]:
        if arc < 0x80:
            body += bytes([arc])
        else:
            chunk = bytes([arc & 0x7F])
            arc >>= 7
            while arc:
                chunk = bytes([(arc & 0x7F) | 0x80]) + chunk
                arc >>= 7
            body += chunk
    return _tlv(T_OID, body)


def enc_timeticks(hundredths: int) -> bytes:
    return enc_int(hundredths, tag=T_TIMETICKS)


def enc_ipaddress(ip: str) -> bytes:
    return _tlv(T_IPADDRESS, bytes(int(o) for o in ip.split(".")))


def enc_counter32(v: int) -> bytes:
    return enc_int(v, tag=T_COUNTER32)


def enc_gauge32(v: int) -> bytes:
    return enc_int(v, tag=T_GAUGE32)


def enc_sequence(*items: bytes) -> bytes:
    return _tlv(T_SEQUENCE, b"".join(items))


# --- decoder ----------------------------------------------------------------
def _dec_len(buf: bytes, i: int):
    b = buf[i]; i += 1
    if b < 0x80:
        return b, i
    n = b & 0x7F
    val = int.from_bytes(buf[i:i + n], "big")
    return val, i + n


def _dec_oid(body: bytes) -> str:
    if not body:
        return ""
    first = body[0]
    arcs = [first // 40, first % 40]
    cur = 0
    for b in body[1:]:
        cur = (cur << 7) | (b & 0x7F)
        if not (b & 0x80):
            arcs.append(cur); cur = 0
    return ".".join(str(a) for a in arcs)


def decode(buf: bytes, i: int = 0):
    """Return (tag, value, next_index). Composite tags yield a list of children."""
    tag = buf[i]; i += 1
    length, i = _dec_len(buf, i)
    body = buf[i:i + length]
    end = i + length
    if tag in (T_SEQUENCE, T_TRAP_V2):
        children = []
        j = 0
        while j < len(body):
            t, v, nj = decode(body, j)
            children.append((t, v))
            j = nj
        return tag, children, end
    if tag == T_OID:
        return tag, _dec_oid(body), end
    if tag in (T_INTEGER, T_TIMETICKS, T_COUNTER32, T_GAUGE32):
        return tag, int.from_bytes(body, "big"), end
    if tag == T_IPADDRESS:
        return tag, ".".join(str(b) for b in body), end
    if tag == T_OCTETSTRING:
        try:
            return tag, body.decode(), end
        except UnicodeDecodeError:
            return tag, body, end
    if tag == T_NULL:
        return tag, None, end
    return tag, body, end
