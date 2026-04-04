from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .model import PetriNet


@dataclass
class MatrixView:
    place_ids: list[str]
    transition_ids: list[str]
    mu: np.ndarray
    d_minus: np.ndarray
    d_plus: np.ndarray
    d: np.ndarray


class PetriMatrixEngine:
    def __init__(self, net: PetriNet):
        self.net = net

    def matrix_view(self) -> MatrixView:
        place_ids = self.net.place_ids()
        transition_ids = self.net.transition_ids()
        p_index = {pid: i for i, pid in enumerate(place_ids)}
        t_index = {tid: i for i, tid in enumerate(transition_ids)}

        d_minus = np.zeros((len(transition_ids), len(place_ids)), dtype=int)
        d_plus = np.zeros((len(transition_ids), len(place_ids)), dtype=int)

        for arc in self.net.arcs:
            source_kind = self.net.node_kind(arc.source)
            target_kind = self.net.node_kind(arc.target)
            if source_kind == "place" and target_kind == "transition":
                d_minus[t_index[arc.target], p_index[arc.source]] += arc.weight
            elif source_kind == "transition" and target_kind == "place":
                d_plus[t_index[arc.source], p_index[arc.target]] += arc.weight
            else:
                raise ValueError(
                    f"Arco inválido {arc.source}->{arc.target}. La red debe ser bipartita lugar/transición."
                )

        mu = np.array([self.net.get_place(pid).tokens for pid in place_ids], dtype=int)
        d = d_plus - d_minus
        return MatrixView(
            place_ids=place_ids,
            transition_ids=transition_ids,
            mu=mu,
            d_minus=d_minus,
            d_plus=d_plus,
            d=d,
        )

    def enabled_transition_ids(self) -> list[str]:
        view = self.matrix_view()
        enabled: list[str] = []
        for j, tid in enumerate(view.transition_ids):
            if np.all(view.mu >= view.d_minus[j]):
                enabled.append(tid)
        return enabled

    def is_enabled(self, transition_id: str) -> bool:
        return transition_id in set(self.enabled_transition_ids())

    def fire(self, transition_id: str) -> np.ndarray:
        view = self.matrix_view()
        if transition_id not in view.transition_ids:
            raise KeyError(f"Transición desconocida: {transition_id}")
        j = view.transition_ids.index(transition_id)
        if not np.all(view.mu >= view.d_minus[j]):
            raise RuntimeError(f"La transición {transition_id} no está habilitada")
        new_mu = view.mu + view.d[j]
        for pid, value in zip(view.place_ids, new_mu.tolist()):
            place = self.net.get_place(pid)
            if place is None:
                raise RuntimeError("Inconsistencia interna en la red")
            place.tokens = int(value)
        return new_mu
