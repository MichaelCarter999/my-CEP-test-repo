"""
engine.py — the deterministic CEP engine.

Holds a sliding time window of active alarms and, on every change, recomputes
correlation. Two rules ship by default (parameterised from rules.yaml):

  topology_reachability   group NODE_DOWN/UNREACHABLE alarms by graph reachability
                          within `window_s`; mark symptoms, attribute root cause.
  flap_dampening          collapse >= `flap_threshold` IF_FLAP/LINK transitions on
                          one interface within `window_s` into one FLAPPING alarm.

Determinism: identical input event ordering always yields identical output. No
scoring, no ML. That is the property that makes it defensible against a
carrier-grade platform for the same use case.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass

from .graph import DependencyGraph
from .models import Alarm, AlarmState


@dataclass
class Metrics:
    ingested: int = 0
    active: int = 0
    symptoms: int = 0
    root_causes: int = 0
    flapping: int = 0
    last_latency_ms: float = 0.0
    suppression_ratio: float = 0.0  # symptoms / (symptoms + root_causes)


class CEPEngine:
    def __init__(self, graph: DependencyGraph, window_s: float = 60.0,
                 flap_threshold: int = 4):
        self.graph = graph
        self.window_s = window_s
        self.flap_threshold = flap_threshold
        self.alarms: dict[str, Alarm] = {}
        self._flaps: dict[tuple[str, str], deque] = defaultdict(deque)
        self.metrics = Metrics()
        self.listeners: list = []  # async callbacks(snapshot)

    # -- ingest --------------------------------------------------------------
    def ingest(self, alarm: Alarm) -> None:
        t0 = time.perf_counter()
        self.metrics.ingested += 1

        if alarm.kind == "CLEAR":
            # recovery: drop any alarms for this device, then re-correlate
            for aid in [a.id for a in self.alarms.values() if a.device == alarm.device]:
                del self.alarms[aid]
            self._flaps.pop((alarm.device, alarm.interface or "?"), None)
        elif alarm.kind in ("IF_FLAP", "LINK_DOWN", "LINK_UP"):
            self._handle_flap(alarm)
        else:
            self.alarms[alarm.id] = alarm

        self._expire()
        self._correlate()
        self.metrics.last_latency_ms = (time.perf_counter() - t0) * 1000.0

    def _handle_flap(self, alarm: Alarm):
        key = (alarm.device, alarm.interface or "?")
        dq = self._flaps[key]
        dq.append(alarm.ts)
        cutoff = alarm.ts - self.window_s
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= self.flap_threshold:
            fid = f"flap:{alarm.device}:{alarm.interface}"
            self.alarms[fid] = Alarm(
                id=fid, device=alarm.device, kind="IF_FLAP",
                interface=alarm.interface, state=AlarmState.FLAPPING,
                severity="warning", ts=alarm.ts, source=alarm.source,
                raw={"transitions": len(dq), "window_s": self.window_s},
            )
        else:
            # below threshold: keep as a normal active alarm
            self.alarms[alarm.id] = alarm

    def _expire(self):
        now = time.time()
        dead = [aid for aid, a in self.alarms.items()
                if now - a.ts > self.window_s and a.state != AlarmState.ROOT_CAUSE]
        for aid in dead:
            del self.alarms[aid]

    # -- correlation (deterministic) ----------------------------------------
    def _correlate(self):
        # 1. failed set = devices with a NODE_DOWN (root failure) alarm in window
        failed = {a.device for a in self.alarms.values() if a.kind == "NODE_DOWN"}

        # 2. reachability impact from the dependency graph
        impact = self.graph.impacted_by(failed) if failed else {}

        # 3. reset transient states (preserve FLAPPING)
        for a in self.alarms.values():
            if a.state != AlarmState.FLAPPING:
                a.state = AlarmState.ACTIVE
                a.root_cause = None
                a.explains = []

        # 4. apply impact: alarms on impacted devices become symptoms; the
        #    failed device they attribute to becomes a root cause
        root_alarm_by_device: dict[str, Alarm] = {}
        for a in self.alarms.values():
            if a.device in failed and a.kind == "NODE_DOWN":
                root_alarm_by_device.setdefault(a.device, a)

        for a in self.alarms.values():
            if a.state == AlarmState.FLAPPING:
                continue
            dev = a.device
            if dev in failed and a.kind == "NODE_DOWN":
                continue  # decided below
            rc = impact.get(dev)
            if rc is not None and rc in root_alarm_by_device:
                # only suppress if within the time window of the root cause
                root = root_alarm_by_device[rc]
                if abs(a.ts - root.ts) <= self.window_s:
                    a.state = AlarmState.SYMPTOM
                    a.root_cause = rc
                    root.explains.append(a.id)

        # 5. mark root causes
        for dev, root in root_alarm_by_device.items():
            root.state = AlarmState.ROOT_CAUSE if root.explains else AlarmState.ACTIVE

        self._recount()

    def _recount(self):
        m = self.metrics
        m.active = sum(1 for a in self.alarms.values() if a.state == AlarmState.ACTIVE)
        m.symptoms = sum(1 for a in self.alarms.values() if a.state == AlarmState.SYMPTOM)
        m.root_causes = sum(1 for a in self.alarms.values() if a.state == AlarmState.ROOT_CAUSE)
        m.flapping = sum(1 for a in self.alarms.values() if a.state == AlarmState.FLAPPING)
        denom = m.symptoms + m.root_causes
        m.suppression_ratio = (m.symptoms / denom) if denom else 0.0

    # -- views ---------------------------------------------------------------
    def snapshot(self) -> dict:
        return {
            "metrics": self.metrics.__dict__,
            "alarms": [a.to_dict() for a in self.alarms.values()],
            "ts": time.time(),
        }

    def clear(self):
        self.alarms.clear()
        self._flaps.clear()
        self._recount()
