from petri_matrix_studio.coverage import CoverageTreeBuilder, OMEGA
from petri_matrix_studio.io import from_dict


def build_unbounded_net():
    # Net analogous to the classic example where t1 grows P1 and t2 moves one token to P2.
    return from_dict(
        {
            "name": "Unbounded",
            "places": [
                {"id": "P1", "label": "P1", "x": 0, "y": 0, "tokens": 1},
                {"id": "P2", "label": "P2", "x": 0, "y": 0, "tokens": 0},
            ],
            "transitions": [
                {"id": "T1", "label": "T1", "x": 0, "y": 0},
                {"id": "T2", "label": "T2", "x": 0, "y": 0},
            ],
            "arcs": [
                {"source": "P1", "target": "T1", "weight": 1},
                {"source": "T1", "target": "P1", "weight": 2},
                {"source": "P1", "target": "T2", "weight": 1},
                {"source": "T2", "target": "P2", "weight": 1},
            ],
        }
    )


def test_coverage_tree_detects_omega_and_duplicates():
    tree = CoverageTreeBuilder(build_unbounded_net()).build()
    markings = {node.marking for node in tree.nodes.values()}
    assert (OMEGA, 0) in markings
    assert any(node.kind == "duplicate" for node in tree.nodes.values())
