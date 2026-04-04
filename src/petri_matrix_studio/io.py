from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .model import Arc, PetriNet, Place, Transition


class PetriJSONError(ValueError):
    pass


def to_dict(net: PetriNet) -> dict[str, Any]:
    return {
        "version": 1,
        "name": net.name,
        "places": [
            {"id": p.id, "label": p.label, "x": p.x, "y": p.y, "tokens": p.tokens}
            for p in net.places
        ],
        "transitions": [
            {"id": t.id, "label": t.label, "x": t.x, "y": t.y}
            for t in net.transitions
        ],
        "arcs": [
            {"source": a.source, "target": a.target, "weight": a.weight}
            for a in net.arcs
        ],
    }


def from_dict(data: dict[str, Any]) -> PetriNet:
    if not isinstance(data, dict):
        raise PetriJSONError("El JSON raíz debe ser un objeto.")
    places = [
        Place(
            id=str(item["id"]),
            label=str(item.get("label", item["id"])),
            x=float(item["x"]),
            y=float(item["y"]),
            tokens=int(item.get("tokens", 0)),
        )
        for item in data.get("places", [])
    ]
    transitions = [
        Transition(
            id=str(item["id"]),
            label=str(item.get("label", item["id"])),
            x=float(item["x"]),
            y=float(item["y"]),
        )
        for item in data.get("transitions", [])
    ]
    net = PetriNet(name=str(data.get("name", "Imported Petri Net")), places=places, transitions=transitions)
    node_ids = set(net.place_ids()) | set(net.transition_ids())
    for item in data.get("arcs", []):
        source = str(item["source"])
        target = str(item["target"])
        if source not in node_ids or target not in node_ids:
            raise PetriJSONError(f"Arco inválido: {source} -> {target}")
        net.arcs.append(Arc(source=source, target=target, weight=max(1, int(item.get("weight", 1)))))
    return net


def save_json(net: PetriNet, path: str | Path) -> None:
    Path(path).write_text(json.dumps(to_dict(net), indent=2, ensure_ascii=False), encoding="utf-8")


def load_json(path: str | Path) -> PetriNet:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return from_dict(raw)
