"""Core data models for the CEP sidecar."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AlarmState(str, Enum):
    ACTIVE = "ACTIVE"
    SYMPTOM = "SYMPTOM"        # explained by a root cause, suppressed
    ROOT_CAUSE = "ROOT_CAUSE"  # the cause of one or more symptoms
    FLAPPING = "FLAPPING"      # damped from many transitions
    CLEARED = "CLEARED"


@dataclass
class Alarm:
    id: str
    device: str
    kind: str                      # NODE_DOWN | UNREACHABLE | LINK_DOWN | IF_FLAP ...
    severity: str = "high"
    ts: float = field(default_factory=time.time)
    interface: Optional[str] = None
    state: AlarmState = AlarmState.ACTIVE
    root_cause: Optional[str] = None
    explains: list[str] = field(default_factory=list)  # symptom ids (if root cause)
    source: str = "sim"            # sim | zabbix
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["state"] = self.state.value
        return d
