"""
Fault-lab integration: proves the real-fault detection path classifies container
state + data-plane reachability into the right event kinds, and that the engine
then correlates them. Uses monitor.classify with a mock probe (no Docker needed).
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "sidecar"))
sys.path.insert(0, os.path.join(ROOT, "faultlab"))

from cep.engine import CEPEngine          # noqa: E402
from cep.graph import DependencyGraph      # noqa: E402
from cep.models import Alarm, AlarmState   # noqa: E402
import monitor as M                        # noqa: E402

TOPO = os.path.join(ROOT, "topology", "topology.json")


def feed(engine, node, kind):
    engine.ingest(Alarm(id=f"{node}:{kind}", device=node, kind=kind, ts=time.time()))


def test_monitor_classify_maps_states():
    """Stopped container -> NODE_DOWN; up-but-cutoff -> UNREACHABLE; ok -> HEALTHY."""
    stopped = {"spur-a1"}
    unreachable = {"10.255.0.32"}
    running = lambda n: n not in stopped
    reach = lambda lo: lo not in unreachable
    assert M.classify("spur-a1", "10.255.0.31", running, reach) == "NODE_DOWN"
    assert M.classify("spur-a2", "10.255.0.32", running, reach) == "UNREACHABLE"
    assert M.classify("core01", "10.255.0.1", running, reach) == "HEALTHY"


def test_real_fault_chain_spur_cascade():
    """spur-a1 down + a2/a3 cut off -> a1 root cause, a2/a3 symptoms; sibling clean."""
    eng = CEPEngine(DependencyGraph.from_file(TOPO), window_s=120)
    feed(eng, "spur-a1", "NODE_DOWN")     # container stopped
    feed(eng, "spur-a2", "UNREACHABLE")   # cut off downstream
    feed(eng, "spur-a3", "UNREACHABLE")
    st = {a.device: a for a in eng.alarms.values()}
    assert st["spur-a1"].state == AlarmState.ROOT_CAUSE
    assert st["spur-a2"].state == AlarmState.SYMPTOM and st["spur-a2"].root_cause == "spur-a1"
    assert st["spur-a3"].state == AlarmState.SYMPTOM
    assert "acc-a1" not in st, "independent sibling leaf must not alarm"


def test_recovery_clears():
    """A CLEAR event for a device removes its alarms."""
    eng = CEPEngine(DependencyGraph.from_file(TOPO), window_s=120)
    feed(eng, "spur-a1", "NODE_DOWN")
    feed(eng, "spur-a2", "UNREACHABLE")
    feed(eng, "spur-a1", "CLEAR")
    feed(eng, "spur-a2", "CLEAR")
    assert len(eng.alarms) == 0
