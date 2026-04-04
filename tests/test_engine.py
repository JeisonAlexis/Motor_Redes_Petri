from petri_matrix_studio.engine import PetriMatrixEngine
from petri_matrix_studio.io import from_dict, to_dict


def build_simple_net():
    return from_dict(
        {
            "name": "Simple net",
            "places": [
                {"id": "P1", "label": "P1", "x": 100, "y": 100, "tokens": 1},
                {"id": "P2", "label": "P2", "x": 300, "y": 100, "tokens": 0},
            ],
            "transitions": [
                {"id": "T1", "label": "T1", "x": 200, "y": 100},
            ],
            "arcs": [
                {"source": "P1", "target": "T1", "weight": 1},
                {"source": "T1", "target": "P2", "weight": 1},
            ],
        }
    )


def test_enabled_and_fire():
    net = build_simple_net()
    engine = PetriMatrixEngine(net)
    assert engine.enabled_transition_ids() == ["T1"]
    mu = engine.fire("T1")
    assert mu.tolist() == [0, 1]
    assert engine.enabled_transition_ids() == []


def test_roundtrip_json():
    net = build_simple_net()
    data = to_dict(net)
    net2 = from_dict(data)
    assert to_dict(net2) == data
