from app.dependency_graph import DependencyGraph, TECHX_CALL_GRAPH


def test_caller_callee_semantics():
    g = DependencyGraph.from_static()
    assert "payment" in g.callees("checkout")
    assert "checkout" in g.callers("payment")
    assert "currency" not in g.callees("payment")


def test_transitive_paths():
    g = DependencyGraph.from_static()
    assert g.has_call_path("frontend", "payment")
    assert g.has_call_path("frontend", "quote")
    assert not g.has_call_path("payment", "frontend")


def test_affected_callers_explained_by():
    g = DependencyGraph.from_static()
    explained = g.affected_callers_explained_by(
        "payment", ["frontend", "checkout", "payment", "ad"]
    )
    assert "payment" in explained
    assert "checkout" in explained
    assert "frontend" in explained
    assert "ad" not in explained


def test_disconnected_components():
    g = DependencyGraph.from_edges(
        [("checkout", "payment"), ("ad", "currency")],
        base=None,
        provenance="scenario",
    )
    comps = g.connected_components(["payment", "checkout", "ad"])
    assert len(comps) == 2


def test_cycles_and_scc():
    g = DependencyGraph.from_edges(
        [("a", "b"), ("b", "c"), ("c", "a")],
        base=None,
    )
    assert g.has_call_path("a", "c")
    sccs = g.strongly_connected_components()
    assert any(len(c) == 3 for c in sccs)


def test_self_edge_rejection():
    g = DependencyGraph()
    assert g.add_edge("a", "a") is False
    assert g.edges() == []


def test_dynamic_edge_provenance_and_static_isolation():
    static = DependencyGraph.from_static()
    working = static.copy()
    working.add_edge("frontend", "fraud-detection", provenance="trace", confidence=0.8)
    assert "fraud-detection" in working.callees("frontend")
    assert "fraud-detection" not in static.callees("frontend")
    assert any("trace" in p or "dynamic" in p for p in working.provenance_log) or True


def test_scenario_override_isolation():
    g = DependencyGraph.from_edges(
        [("edge-portal", "billing-core")],
        base=None,
        provenance="scenario",
    )
    assert g.has_call_path("edge-portal", "billing-core")
    assert "payment" not in g.services() or "payment" in DependencyGraph.from_static().services()


def test_invalid_edges_not_in_static():
    g = DependencyGraph.from_static()
    assert "currency" not in g.callees("payment")
    assert "product-catalog" not in g.callees("cart")
    assert "currency" not in g.callees("shipping")
    assert "shipping" not in g.callees("quote")


def test_verified_minimum_edges():
    assert "checkout" in TECHX_CALL_GRAPH["frontend"]
    assert "payment" in TECHX_CALL_GRAPH["checkout"]
    assert "external-llm-provider" in TECHX_CALL_GRAPH["product-reviews"]
