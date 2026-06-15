"""
CEP correlation test plan.

Executable specification for the engine in sidecar/cep. Every behavioural claim
in docs/SALES-PITCH.md has a test here, so the demo's claims are verifiable, not
asserted. Run with `pytest -q` from the repo root (conftest writes the JSON the
rich report renders).

Scenarios:
  1. spur_cascade        unprotected chain head fails -> full downstream suppression
  2. dist_blackhole      ring gateway fails -> whole ring + spurs suppressed (high ratio)
  3. ring_protected      one RSTP ring member fails -> peers NOT suppressed
  4. core_redundant      one core of a dual core fails -> nothing downstream lost
  5. precision           cascade + independent faults -> only the dependent ones suppress
  6. flap_dampening      interface flap storm -> single FLAPPING alarm
  7. determinism         identical input ordering -> identical output
"""
import os
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "sidecar"))

from cep.engine import CEPEngine            # noqa: E402
from cep.graph import DependencyGraph        # noqa: E402
from cep.models import Alarm, AlarmState     # noqa: E402

TOPO = os.path.join(ROOT, "topology", "topology.json")


@pytest.fixture
def graph():
    return DependencyGraph.from_file(TOPO)


@pytest.fixture
def engine(graph):
    return CEPEngine(graph, window_s=300.0)


def down(dev, ts=None):
    return Alarm(id=f"{dev}:down", device=dev, kind="NODE_DOWN", ts=ts or time.time())


def unreach(dev, ts=None):
    return Alarm(id=f"{dev}:unreach", device=dev, kind="UNREACHABLE", ts=ts or time.time())


def states(engine):
    return {a.device: a.state for a in engine.alarms.values()}


def test_spur_cascade(engine, graph):
    """Unprotected spur head fails — every node down the chain is suppressed as a symptom."""
    head = "spur-c1"
    kids = graph.descendants(head)              # spur-c2..c4 depend on spur-c1
    assert kids, "spur-c1 should have downstream nodes"
    t = time.time()
    engine.ingest(down(head, t))
    for i, k in enumerate(kids):
        engine.ingest(unreach(k, t + 0.1 * (i + 1)))
    st = states(engine)
    assert st[head] == AlarmState.ROOT_CAUSE
    for k in kids:
        assert st[k] == AlarmState.SYMPTOM, f"{k} should be a symptom of {head}"


def test_dist_blackhole_high_ratio(engine, graph):
    """Ring gateway fails — whole ring plus its spurs collapse to one root cause (>80% suppression)."""
    dist = "dist03"
    kids = graph.descendants(dist)
    t = time.time()
    engine.ingest(down(dist, t))
    for i, k in enumerate(kids):
        engine.ingest(unreach(k, t + 0.05 * (i + 1)))
    assert engine.metrics.root_causes == 1
    assert engine.metrics.symptoms >= 6        # ring C (6) + its spurs
    assert engine.metrics.suppression_ratio > 0.8


def test_ring_member_protected(engine):
    """One RSTP ring member fails — peers reach the core another way and are NOT suppressed."""
    # acc-a3 fails; ring peers reach the core via their own gateway edges,
    # so RSTP protection means they must NOT be suppressed.
    t = time.time()
    engine.ingest(down("acc-a3", t))
    for peer in ("acc-a2", "acc-a4", "acc-a5"):
        engine.ingest(unreach(peer, t + 0.2))
    st = states(engine)
    for peer in ("acc-a2", "acc-a4", "acc-a5"):
        assert st[peer] == AlarmState.ACTIVE, f"{peer} must stay active (RSTP protected)"


def test_core_redundant_no_suppression(engine):
    """One core of a dual-homed pair fails — nothing downstream is lost, so nothing is suppressed."""
    # one core of a dual-homed pair fails; distribution still reaches core02.
    t = time.time()
    engine.ingest(down("core01", t))
    for d in ("dist01", "dist02", "dist03"):
        engine.ingest(unreach(d, t + 0.2))
    st = states(engine)
    for d in ("dist01", "dist02", "dist03"):
        assert st[d] == AlarmState.ACTIVE, f"{d} survivable via core02 — not a symptom"
    # core01 explains nobody, so it is not a root cause
    assert st["core01"] == AlarmState.ACTIVE


def test_precision_independent_faults(engine, graph):
    """Two unrelated faults at once — each attributes to its own root cause, no cross-contamination."""
    # dist03 cascade PLUS two unrelated failures that must survive uncorrelated.
    t = time.time()
    engine.ingest(down("dist03", t))
    for i, k in enumerate(graph.descendants("dist03")):
        engine.ingest(unreach(k, t + 0.05 * (i + 1)))
    # independent second fault on a different branch: spur-b1 head down, and its
    # downstream spur-b2 unreachable. This must attribute to spur-b1, NOT dist03.
    engine.ingest(down("spur-b1", t + 1))
    engine.ingest(unreach("spur-b2", t + 1.1))
    st = states(engine)
    # two distinct, correctly separated root causes
    assert st["dist03"] == AlarmState.ROOT_CAUSE
    assert st["spur-b1"] == AlarmState.ROOT_CAUSE
    sb2 = next(a for a in engine.alarms.values() if a.device == "spur-b2")
    assert sb2.root_cause == "spur-b1", "spur-b2 must attribute to spur-b1, not dist03"


def test_flap_dampening(engine):
    """Interface flap storm collapses into a single FLAPPING alarm."""
    t = time.time()
    for i in range(8):
        engine.ingest(Alarm(id=f"f{i}", device="acc-b2", kind="IF_FLAP",
                            interface="eth2", ts=t + i * 0.5))
    flapping = [a for a in engine.alarms.values() if a.state == AlarmState.FLAPPING]
    assert len(flapping) == 1
    assert flapping[0].raw.get("transitions", 0) >= 4


def test_determinism(graph):
    """Identical input ordering yields byte-identical correlation output — no scoring, no ML."""
    def run():
        e = CEPEngine(graph, window_s=300.0)
        t = 1_000_000.0
        e.ingest(down("dist01", t))
        for i, k in enumerate(sorted(graph.descendants("dist01"))):
            e.ingest(unreach(k, t + 0.05 * (i + 1)))
        return e.metrics.suppression_ratio, e.metrics.symptoms, e.metrics.root_causes
    assert run() == run()


def test_classify_enrichment_contract(graph):
    """Topology enrichment (/classify): cause, symptom and RSTP-protected independent."""
    # dist03 down: it is the cause; ring-C members attribute to it as symptoms.
    impact = graph.impacted_by({"dist03"})
    assert impact.get("acc-c2") == "dist03"          # symptom -> cep_root=dist03
    assert impact.get("spur-c3") == "dist03"         # transitively a symptom
    assert "dist03" not in impact or impact["dist03"] is None  # the cause itself
    # one ring switch down: a peer stays independent (RSTP protected, reaches core)
    impact2 = graph.impacted_by({"acc-a3"})
    assert "acc-a4" not in impact2, "ring peer must classify as independent"
    # single core down: distribution is not a symptom (dual-homed redundancy)
    impact3 = graph.impacted_by({"core01"})
    assert "dist01" not in impact3
