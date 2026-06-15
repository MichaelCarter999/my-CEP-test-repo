"""
graph.py — topology dependency graph for reachability-based correlation.

The graph is directed: an edge child -> parent means "child needs parent to
reach the network core". Reachability to ANY core node is what defines whether
a device is up. This single model captures three behaviours correctly:

  * spur chains      single path  -> head failure cascades to all below it
  * RSTP rings       each member has its own gateway edge, peers are NOT on each
                     other's path -> one ring switch failing isolates nobody
  * dual-homing/core multiple paths -> single failure is survivable

This is intentionally NOT naive parent-down suppression. We remove the failed
set from the graph and ask "who can no longer reach a core?". Anyone who can't
is a symptom; the failed device on their blocked path is the root cause.
"""
from __future__ import annotations

import json
from typing import Iterable

import networkx as nx


class DependencyGraph:
    def __init__(self, model: dict):
        self.model = model
        self.g = nx.DiGraph()
        self.cores: set[str] = set()
        self._build()

    @classmethod
    def from_file(cls, path: str) -> "DependencyGraph":
        with open(path) as f:
            return cls(json.load(f))

    def _build(self):
        for d in self.model["devices"]:
            if d["layer"] == "passive":
                continue
            self.g.add_node(d["name"], role=d["role"], protected=d["protected"],
                            layer=d["layer"])
            if d["role"] == "core":
                self.cores.add(d["name"])
        for dep in self.model["dependencies"]:
            # child -> parent (direction of "I depend on you to reach the core")
            self.g.add_edge(dep["child"], dep["parent"],
                            relation=dep["relation"], protected=dep["protected"])

    # -- reachability --------------------------------------------------------
    def reaches_core(self, node: str, failed: set[str]) -> bool:
        """True if node can reach any core with `failed` devices removed."""
        if node in failed:
            return False
        if node in self.cores:
            return True
        seen = {node}
        stack = [node]
        while stack:
            cur = stack.pop()
            for parent in self.g.successors(cur):
                if parent in failed or parent in seen:
                    continue
                if parent in self.cores:
                    return True
                seen.add(parent)
                stack.append(parent)
        return False

    def impacted_by(self, failed: set[str]) -> dict[str, str | None]:
        """
        Given a set of failed devices, return {device: root_cause} for every
        device that can no longer reach a core. root_cause is the nearest failed
        ancestor on the device's path (None if the device itself is in failed).
        """
        result: dict[str, str | None] = {}
        for node in self.g.nodes:
            if node in failed:
                result[node] = None  # it is itself (a) root cause
                continue
            if not self.reaches_core(node, failed):
                result[node] = self._nearest_failed_ancestor(node, failed)
        return result

    def _nearest_failed_ancestor(self, node: str, failed: set[str]) -> str | None:
        """BFS upward; return the closest failed device blocking the path."""
        seen = {node}
        queue = [(node, 0)]
        best, best_hop = None, 10 ** 9
        while queue:
            cur, hop = queue.pop(0)
            for parent in self.g.successors(cur):
                if parent in failed and hop + 1 < best_hop:
                    best, best_hop = parent, hop + 1
                if parent not in seen and parent not in failed:
                    seen.add(parent)
                    queue.append((parent, hop + 1))
        return best

    def descendants(self, node: str) -> set[str]:
        """All devices that have `node` on a path toward the core (predecessors)."""
        return set(nx.ancestors(self.g, node)) if node in self.g else set()

    def node_count(self) -> int:
        return self.g.number_of_nodes()
