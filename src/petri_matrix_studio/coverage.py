from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Sequence

from .engine import PetriMatrixEngine
from .model import PetriNet

OMEGA = "ω"
MarkValue = int | str
Marking = tuple[MarkValue, ...]


@dataclass(slots=True)
class CoverageNode:
    node_id: int
    marking: Marking
    parent_id: int | None = None
    via_transition: str | None = None
    kind: str = "frontier"  # frontier, terminal, duplicate, internal
    children_ids: list[int] = field(default_factory=list)
    duplicate_of: int | None = None


@dataclass(slots=True)
class CoverageTree:
    place_ids: list[str]
    transition_ids: list[str]
    root_id: int
    nodes: dict[int, CoverageNode]

    def children_of(self, node_id: int) -> list[CoverageNode]:
        return [self.nodes[child_id] for child_id in self.nodes[node_id].children_ids]


class CoverageTreeBuilder:
    def __init__(self, net: PetriNet):
        self.net = net
        self.engine = PetriMatrixEngine(net)
        self.view = self.engine.matrix_view()
        self.place_ids = self.view.place_ids
        self.transition_ids = self.view.transition_ids
        self._next_id = 0

    def build(self) -> CoverageTree:
        root_marking: Marking = tuple(int(v) for v in self.view.mu.tolist())
        root = CoverageNode(node_id=self._new_id(), marking=root_marking)
        nodes: dict[int, CoverageNode] = {root.node_id: root}
        frontier: list[int] = [root.node_id]

        while frontier:
            node_id = frontier.pop(0)
            node = nodes[node_id]
            if node.kind != "frontier":
                continue

            duplicate_of = self._find_duplicate(nodes, node)
            if duplicate_of is not None:
                node.kind = "duplicate"
                node.duplicate_of = duplicate_of
                continue

            enabled = self._enabled_transition_indices(node.marking)
            if not enabled:
                node.kind = "terminal"
                continue

            for j in enabled:
                raw_successor = self._fire_marking(node.marking, j)
                accelerated = self._accelerate(node_id, raw_successor, nodes)
                child = CoverageNode(
                    node_id=self._new_id(),
                    marking=accelerated,
                    parent_id=node_id,
                    via_transition=self.transition_ids[j],
                    kind="frontier",
                )
                nodes[child.node_id] = child
                node.children_ids.append(child.node_id)
                frontier.append(child.node_id)
            node.kind = "internal"

        return CoverageTree(
            place_ids=self.place_ids,
            transition_ids=self.transition_ids,
            root_id=root.node_id,
            nodes=nodes,
        )

    def _new_id(self) -> int:
        nid = self._next_id
        self._next_id += 1
        return nid

    def _find_duplicate(self, nodes: dict[int, CoverageNode], node: CoverageNode) -> int | None:
        for other in nodes.values():
            if other.node_id == node.node_id:
                continue
            if other.kind == "frontier":
                continue
            if other.marking == node.marking:
                return other.node_id
        return None

    def _enabled_transition_indices(self, marking: Marking) -> list[int]:
        enabled: list[int] = []
        for j in range(len(self.transition_ids)):
            ok = True
            for i in range(len(self.place_ids)):
                need = int(self.view.d_minus[j, i])
                have = marking[i]
                if have != OMEGA and int(have) < need:
                    ok = False
                    break
            if ok:
                enabled.append(j)
        return enabled

    def _fire_marking(self, marking: Marking, transition_index: int) -> Marking:
        out: list[MarkValue] = []
        for i in range(len(self.place_ids)):
            value = marking[i]
            if value == OMEGA:
                out.append(OMEGA)
            else:
                new_value = int(value) - int(self.view.d_minus[transition_index, i]) + int(self.view.d_plus[transition_index, i])
                if new_value < 0:
                    raise RuntimeError("La construcción del árbol encontró una marcación negativa")
                out.append(new_value)
        return tuple(out)

    def _accelerate(self, node_id: int, marking: Marking, nodes: dict[int, CoverageNode]) -> Marking:
        current = list(marking)
        ancestors = self._ancestor_chain(node_id, nodes)
        changed = True
        while changed:
            changed = False
            for ancestor in ancestors:
                anc_marking = ancestor.marking
                if self._leq_marking(anc_marking, tuple(current)) and anc_marking != tuple(current):
                    for i, (a, b) in enumerate(zip(anc_marking, current)):
                        if self._lt_value(a, b) and current[i] != OMEGA:
                            current[i] = OMEGA
                            changed = True
        return tuple(current)

    def _ancestor_chain(self, node_id: int, nodes: dict[int, CoverageNode]) -> list[CoverageNode]:
        chain: list[CoverageNode] = []
        cursor = nodes[node_id]
        while True:
            chain.append(cursor)
            if cursor.parent_id is None:
                break
            cursor = nodes[cursor.parent_id]
        chain.reverse()
        return chain

    @staticmethod
    def _leq_marking(left: Marking, right: Marking) -> bool:
        return all(CoverageTreeBuilder._leq_value(a, b) for a, b in zip(left, right))

    @staticmethod
    def _leq_value(left: MarkValue, right: MarkValue) -> bool:
        if right == OMEGA:
            return True
        if left == OMEGA:
            return right == OMEGA
        return int(left) <= int(right)

    @staticmethod
    def _lt_value(left: MarkValue, right: MarkValue) -> bool:
        return CoverageTreeBuilder._leq_value(left, right) and left != right


def format_marking(marking: Sequence[MarkValue]) -> str:
    return "(" + ", ".join(str(v) for v in marking) + ")"
