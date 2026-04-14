from __future__ import annotations

from collections import deque
from copy import deepcopy
from typing import Dict, List, Optional, Set, Tuple

from .engine import PetriMatrixEngine
from .coverage import CoverageTree, CoverageTreeBuilder, OMEGA
from .model import PetriNet


def verify_sequence(net: PetriNet, sequence: List[str]) -> Tuple[bool, Optional[int], Optional[Dict[str, int]]]:

    test_net = deepcopy(net)
    engine = PetriMatrixEngine(test_net)
    marking = engine.matrix_view().mu.copy()

    for i, tid in enumerate(sequence):
        if tid not in engine.matrix_view().transition_ids:
            return (
                False,
                i,
                {
                    pid: int(marking[idx])
                    for idx, pid in enumerate(engine.matrix_view().place_ids)
                },
            )
        if not engine.is_enabled(tid):
            return (
                False,
                i,
                {
                    pid: int(marking[idx])
                    for idx, pid in enumerate(engine.matrix_view().place_ids)
                },
            )
        engine.fire(tid)
        marking = engine.matrix_view().mu
    return True, None, None


def exact_reachability(
    net: PetriNet,
    target_marking: Dict[str, int],
    max_depth: int = 1000,
    max_states: int = 10000,
) -> Tuple[Optional[bool], Optional[List[str]]]:
   
   #Detectar si la red es no acotada
    try:
        # Construye el árbol de cobertura
        tree = CoverageTreeBuilder(net).build()
        # Revisa si existe ω en alguna marcación → indica crecimiento infinito
        unbounded = any(OMEGA in node.marking for node in tree.nodes.values())
    except Exception:
        unbounded = False  

    # BFS (búsqueda en anchura)
    start_net = deepcopy(net)
    start_engine = PetriMatrixEngine(start_net)
    start_marking = start_engine.matrix_view().mu
    start_tuple = tuple(int(v) for v in start_marking)

    target_tuple = tuple(
        target_marking.get(pid, 0) for pid in start_engine.matrix_view().place_ids
    )

    #ya estamos en la marcación objetivo
    if start_tuple == target_tuple:
        return True, []

    queue = deque()
    queue.append((start_tuple, []))
    visited = {start_tuple}
    states_explored = 0

    while queue and len(visited) <= max_states:
        # Sacamos el siguiente estado a explorar
        current_marking, path = queue.popleft()
        
        if len(path) > max_depth:
            continue

        test_net = deepcopy(net)
        test_engine = PetriMatrixEngine(test_net)
        
        for i, pid in enumerate(test_engine.matrix_view().place_ids):
            test_net.get_place(pid).tokens = current_marking[i]
        test_engine = PetriMatrixEngine(test_net)  

        for tid in test_engine.matrix_view().transition_ids:
            if test_engine.is_enabled(tid):
                new_engine = deepcopy(test_engine)
                new_engine.fire(tid)
                new_marking = new_engine.matrix_view().mu
                new_tuple = tuple(int(v) for v in new_marking)
                
                # Si llegamos al objetiv
                if new_tuple == target_tuple:
                    return True, path + [tid]
                
                # Marcar como visitado
                if new_tuple not in visited:
                    visited.add(new_tuple)
                    queue.append((new_tuple, path + [tid]))
                    
        states_explored += 1
        if states_explored > max_states:
            break

    # No se puede asegurar (la red puede crecer infinito)
    if unbounded:
        return None, None  
    else:
        return False, None
    #la red esta acotada


def coverability(net: PetriNet, target_marking: Dict[str, int]) -> bool:
    """Verifica si existe una marcación ≥ target_marking en el árbol de cobertura."""
    tree = CoverageTreeBuilder(net).build()
    place_ids = tree.place_ids
    target_vec = [target_marking.get(pid, 0) for pid in place_ids]

    def geq(marking, target):
        for m, t in zip(marking, target):
            if m != OMEGA and int(m) < t:
                return False
        return True

    for node in tree.nodes.values():
        if geq(node.marking, target_vec):
            return True
    return False


def detect_deadlock(engine: PetriMatrixEngine) -> bool:
    """Retorna True si no hay transiciones habilitadas (bloqueo)."""
    return len(engine.enabled_transition_ids()) == 0


def detect_bottlenecks(net: PetriNet, factor: float = 2.0) -> List[Tuple[str, int]]:
    """
    Detecta lugares con acumulación de tokens.
    Criterio: tokens > (promedio * factor).
    Retorna lista de (id_lugar, tokens).
    """
    tokens = [p.tokens for p in net.places]
    if not tokens:
        return []
    avg = sum(tokens) / len(tokens)
    threshold = avg * factor
    return [(p.id, p.tokens) for p in net.places if p.tokens > threshold]


def detect_dead_transitions(
    net: PetriNet, max_states: int = 5000, max_depth: int = 100
) -> Set[str]:
    """
    Detecta transiciones que nunca se disparan en el espacio de alcanzabilidad.
    Retorna conjunto de IDs de transiciones muertas.
    """
    all_transitions = set(net.transition_ids())
    fired = set()

    # BFS limitada
    start_net = deepcopy(net)
    start_engine = PetriMatrixEngine(start_net)
    start_marking = start_engine.matrix_view().mu
    start_tuple = tuple(int(v) for v in start_marking)

    queue = deque()
    queue.append((start_tuple, 0))
    visited = {start_tuple}
    states = 0

    while queue and states < max_states:
        current_marking, depth = queue.popleft()
        if depth > max_depth:
            continue

        # Restaurar estado
        test_net = deepcopy(net)
        test_engine = PetriMatrixEngine(test_net)
        for i, pid in enumerate(test_engine.matrix_view().place_ids):
            test_net.get_place(pid).tokens = current_marking[i]
        test_engine = PetriMatrixEngine(test_net)

        for tid in test_engine.matrix_view().transition_ids:
            if test_engine.is_enabled(tid):
                fired.add(tid)
                new_engine = deepcopy(test_engine)
                new_engine.fire(tid)
                new_marking = new_engine.matrix_view().mu
                new_tuple = tuple(int(v) for v in new_marking)
                if new_tuple not in visited:
                    visited.add(new_tuple)
                    queue.append((new_tuple, depth + 1))
        states += 1

    return all_transitions - fired


def boundedness(net: PetriNet) -> Tuple[bool, List[str]]:
    """
    Determina si la red es acotada (sin ω en el árbol de cobertura).
    Retorna (acotada, lista de lugares no acotados).
    """
    tree = CoverageTreeBuilder(net).build()
    unbounded_places = []
    place_ids = tree.place_ids
    for idx, pid in enumerate(place_ids):
        if any(node.marking[idx] == OMEGA for node in tree.nodes.values()):
            unbounded_places.append(pid)
    return len(unbounded_places) == 0, unbounded_places
