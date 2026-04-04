from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

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

    # --- Métodos nuevos ---
    def get_marking_tuple(self) -> Tuple[int, ...]:
        """Retorna el marcado actual como tupla de enteros."""
        view = self.matrix_view()
        return tuple(int(v) for v in view.mu)

    def get_marking_dict(self) -> dict[str, int]:
        """Retorna el marcado actual como diccionario {id_lugar: tokens}."""
        view = self.matrix_view()
        return {pid: int(view.mu[i]) for i, pid in enumerate(view.place_ids)}

    def set_marking_from_tuple(self, marking: Tuple[int, ...]) -> None:
        """Restaura el marcado a partir de una tupla (debe coincidir el orden de places)."""
        view = self.matrix_view()
        if len(marking) != len(view.place_ids):
            raise ValueError("La tupla no coincide con la cantidad de lugares")
        for i, pid in enumerate(view.place_ids):
            place = self.net.get_place(pid)
            if place is not None:
                place.tokens = marking[i]

    def fire_sequence(self, sequence: List[str]) -> List[Tuple[int, ...]]:
        """
        Dispara una secuencia de transiciones.
        Retorna una lista de marcados intermedios (tuplas).
        Lanza excepción si alguna transición no está habilitada.
        """
        markings = [self.get_marking_tuple()]
        for tid in sequence:
            if not self.is_enabled(tid):
                raise RuntimeError(f"Transición {tid} no habilitada en {markings[-1]}")
            self.fire(tid)
            markings.append(self.get_marking_tuple())
        return markings