"""Caller -> callee dependency graph for cross-service RCA.

Edge direction is always caller -> callee. Failure impact propagates in the
reverse direction (callee failure hurts callers).
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Iterable, Mapping


# Verified from frontend API routes, checkout gRPC clients, shipping->quote,
# and product-reviews -> product-catalog / external LLM boundary.
# Do NOT add: payment->currency, cart->product-catalog, shipping->currency,
# quote->shipping (those were previously proposed and rejected).
TECHX_CALL_GRAPH: dict[str, frozenset[str]] = {
    "frontend": frozenset(
        {
            "ad",
            "cart",
            "checkout",
            "currency",
            "product-catalog",
            "product-reviews",
            "recommendation",
            "shipping",
        }
    ),
    "checkout": frozenset(
        {
            "cart",
            "currency",
            "email",
            "payment",
            "product-catalog",
            "shipping",
        }
    ),
    "product-reviews": frozenset({"product-catalog", "external-llm-provider"}),
    "shipping": frozenset({"quote"}),
    "recommendation": frozenset({"product-catalog"}),
    "cart": frozenset(),
    "payment": frozenset(),
    "currency": frozenset(),
    "email": frozenset(),
    "ad": frozenset(),
    "product-catalog": frozenset(),
    "quote": frozenset(),
    "external-llm-provider": frozenset(),
}


@dataclass(frozen=True)
class GraphEdge:
    caller: str
    callee: str
    provenance: str = "static"
    confidence: float = 1.0


@dataclass
class DependencyGraph:
    """Mutable analysis-window graph. Static base is never permanently mutated."""

    _callees: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    _callers: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    _edge_meta: dict[tuple[str, str], GraphEdge] = field(default_factory=dict)
    provenance_log: list[str] = field(default_factory=list)

    @classmethod
    def from_static(
        cls,
        static_graph: Mapping[str, Iterable[str]] | None = None,
    ) -> "DependencyGraph":
        graph = cls()
        source = static_graph if static_graph is not None else TECHX_CALL_GRAPH
        for caller, callees in source.items():
            for callee in callees:
                graph.add_edge(caller, callee, provenance="static", confidence=1.0)
            # Ensure isolated nodes exist in adjacency maps.
            graph._callees.setdefault(caller, set())
            graph._callers.setdefault(caller, set())
            for callee in callees:
                graph._callees.setdefault(callee, set())
                graph._callers.setdefault(callee, set())
        graph.provenance_log.append("static:techx-verified")
        return graph

    @classmethod
    def from_edges(
        cls,
        edges: Iterable[tuple[str, str] | GraphEdge | Mapping[str, str]],
        *,
        base: "DependencyGraph | None" = None,
        provenance: str = "scenario",
    ) -> "DependencyGraph":
        graph = base.copy() if base is not None else cls()
        for item in edges:
            if isinstance(item, GraphEdge):
                graph.add_edge(
                    item.caller,
                    item.callee,
                    provenance=item.provenance,
                    confidence=item.confidence,
                )
            elif isinstance(item, Mapping):
                caller = str(item.get("caller") or item.get("from") or "")
                callee = str(item.get("callee") or item.get("to") or "")
                conf = float(item.get("confidence", 1.0))
                prov = str(item.get("provenance") or provenance)
                graph.add_edge(caller, callee, provenance=prov, confidence=conf)
            else:
                caller, callee = item
                graph.add_edge(str(caller), str(callee), provenance=provenance)
        if edges:
            graph.provenance_log.append(f"{provenance}:edges")
        return graph

    def copy(self) -> "DependencyGraph":
        clone = DependencyGraph()
        for (caller, callee), meta in self._edge_meta.items():
            clone.add_edge(
                caller,
                callee,
                provenance=meta.provenance,
                confidence=meta.confidence,
            )
        for service in set(self._callees) | set(self._callers):
            clone._callees.setdefault(service, set())
            clone._callers.setdefault(service, set())
        clone.provenance_log = list(self.provenance_log)
        return clone

    def add_edge(
        self,
        caller: str,
        callee: str,
        *,
        provenance: str = "dynamic",
        confidence: float = 1.0,
    ) -> bool:
        caller = (caller or "").strip()
        callee = (callee or "").strip()
        if not caller or not callee:
            return False
        if caller == callee:
            return False
        key = (caller, callee)
        existing = self._edge_meta.get(key)
        if existing and existing.provenance == "static" and provenance != "static":
            # Keep static edge; record dynamic corroboration without mutating confidence below.
            self.provenance_log.append(
                f"dynamic-corroboration:{caller}->{callee}:{provenance}"
            )
            return True
        self._callees[caller].add(callee)
        self._callers[callee].add(caller)
        self._callees.setdefault(callee, set())
        self._callers.setdefault(caller, set())
        self._edge_meta[key] = GraphEdge(
            caller=caller,
            callee=callee,
            provenance=provenance,
            confidence=max(0.0, min(1.0, float(confidence))),
        )
        return True

    def services(self) -> set[str]:
        return set(self._callees) | set(self._callers)

    def callees(self, service: str) -> frozenset[str]:
        return frozenset(self._callees.get(service, set()))

    def callers(self, service: str) -> frozenset[str]:
        return frozenset(self._callers.get(service, set()))

    def edges(self) -> list[GraphEdge]:
        return sorted(
            self._edge_meta.values(),
            key=lambda e: (e.caller, e.callee, e.provenance),
        )

    def reachable_callees(self, service: str) -> frozenset[str]:
        return self._bfs(service, self._callees)

    def reachable_callers(self, service: str) -> frozenset[str]:
        return self._bfs(service, self._callers)

    def _bfs(self, start: str, adjacency: Mapping[str, set[str]]) -> frozenset[str]:
        if start not in adjacency and start not in self.services():
            return frozenset()
        seen: set[str] = set()
        queue: deque[str] = deque([start])
        while queue:
            node = queue.popleft()
            for nxt in adjacency.get(node, set()):
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        return frozenset(seen)

    def has_call_path(self, caller: str, callee: str) -> bool:
        if caller == callee:
            return True
        return callee in self.reachable_callees(caller)

    def affected_callers_explained_by(
        self,
        candidate: str,
        affected_services: Iterable[str],
    ) -> frozenset[str]:
        """Affected services that can call into the candidate (directly/transitively).

        If candidate fails, those callers are potential downstream victims
        (failure-impact direction is reverse of call edges).
        """

        affected = {s for s in affected_services if s}
        if not affected:
            return frozenset()
        reachable_callers = self.reachable_callers(candidate)
        explained = {
            service
            for service in affected
            if service == candidate or service in reachable_callers
        }
        return frozenset(explained)

    def connected_components(self, services: Iterable[str]) -> list[frozenset[str]]:
        """Undirected connected components over the induced subgraph."""

        nodes = {s for s in services if s}
        if not nodes:
            return []
        undirected: dict[str, set[str]] = defaultdict(set)
        for service in nodes:
            for callee in self._callees.get(service, set()):
                if callee in nodes:
                    undirected[service].add(callee)
                    undirected[callee].add(service)
            for caller in self._callers.get(service, set()):
                if caller in nodes:
                    undirected[service].add(caller)
                    undirected[caller].add(service)
            undirected.setdefault(service, set())

        remaining = set(nodes)
        components: list[frozenset[str]] = []
        while remaining:
            start = min(remaining)  # deterministic
            stack = [start]
            component: set[str] = set()
            while stack:
                node = stack.pop()
                if node in component:
                    continue
                component.add(node)
                for nxt in undirected.get(node, set()):
                    if nxt not in component:
                        stack.append(nxt)
            remaining -= component
            components.append(frozenset(component))
        components.sort(key=lambda c: (len(c), sorted(c)))
        return components

    def strongly_connected_components(self) -> list[frozenset[str]]:
        """Tarjan SCC; used when cycles must be condensed."""

        index = 0
        stack: list[str] = []
        on_stack: set[str] = set()
        indices: dict[str, int] = {}
        lowlink: dict[str, int] = {}
        result: list[frozenset[str]] = []
        nodes = sorted(self.services())

        def strongconnect(node: str) -> None:
            nonlocal index
            indices[node] = index
            lowlink[node] = index
            index += 1
            stack.append(node)
            on_stack.add(node)
            for nxt in sorted(self._callees.get(node, set())):
                if nxt not in indices:
                    strongconnect(nxt)
                    lowlink[node] = min(lowlink[node], lowlink[nxt])
                elif nxt in on_stack:
                    lowlink[node] = min(lowlink[node], indices[nxt])
            if lowlink[node] == indices[node]:
                component: set[str] = set()
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    component.add(w)
                    if w == node:
                        break
                result.append(frozenset(component))

        for node in nodes:
            if node not in indices:
                strongconnect(node)
        result.sort(key=lambda c: (len(c), sorted(c)))
        return result
