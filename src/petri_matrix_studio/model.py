from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(slots=True)
class Place:
    id: str
    label: str
    x: float
    y: float
    tokens: int = 0


@dataclass(slots=True)
class Transition:
    id: str
    label: str
    x: float
    y: float


@dataclass(slots=True)
class Arc:
    source: str
    target: str
    weight: int = 1


@dataclass
class PetriNet:
    name: str = "Untitled Petri Net"
    places: List[Place] = field(default_factory=list)
    transitions: List[Transition] = field(default_factory=list)
    arcs: List[Arc] = field(default_factory=list)

    def place_ids(self) -> List[str]:
        return [p.id for p in self.places]

    def transition_ids(self) -> List[str]:
        return [t.id for t in self.transitions]

    def get_place(self, node_id: str) -> Optional[Place]:
        return next((p for p in self.places if p.id == node_id), None)

    def get_transition(self, node_id: str) -> Optional[Transition]:
        return next((t for t in self.transitions if t.id == node_id), None)

    def get_node(self, node_id: str) -> Optional[Place | Transition]:
        return self.get_place(node_id) or self.get_transition(node_id)

    def node_kind(self, node_id: str) -> Optional[str]:
        if self.get_place(node_id):
            return "place"
        if self.get_transition(node_id):
            return "transition"
        return None

    def has_arc(self, source: str, target: str) -> bool:
        return any(a.source == source and a.target == target for a in self.arcs)

    def get_arc(self, source: str, target: str) -> Optional[Arc]:
        return next((a for a in self.arcs if a.source == source and a.target == target), None)

    def upsert_arc(self, source: str, target: str, weight: int = 1) -> Arc:
        existing = self.get_arc(source, target)
        if existing is not None:
            existing.weight = max(1, int(weight))
            return existing
        arc = Arc(source=source, target=target, weight=max(1, int(weight)))
        self.arcs.append(arc)
        return arc

    def remove_arc(self, source: str, target: str) -> None:
        self.arcs = [a for a in self.arcs if not (a.source == source and a.target == target)]

    def remove_node(self, node_id: str) -> None:
        self.places = [p for p in self.places if p.id != node_id]
        self.transitions = [t for t in self.transitions if t.id != node_id]
        self.arcs = [a for a in self.arcs if a.source != node_id and a.target != node_id]

    def next_place_id(self) -> str:
        i = 1
        existing = set(self.place_ids())
        while f"P{i}" in existing:
            i += 1
        return f"P{i}"

    def next_transition_id(self) -> str:
        i = 1
        existing = set(self.transition_ids())
        while f"T{i}" in existing:
            i += 1
        return f"T{i}"

    def marking_dict(self) -> Dict[str, int]:
        return {p.id: p.tokens for p in self.places}
