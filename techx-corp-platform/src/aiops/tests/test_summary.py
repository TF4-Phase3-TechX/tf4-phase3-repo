from app.models import Evidence, Incident
from app.summary import IncidentSummaryGenerator


def incident() -> Incident:
    return Incident(
        incident_type="llm_timeout_error",
        severity="high",
        affected_service="product-reviews",
        environment="production",
        tenant_id="tenant-42",
        confidence=0.83,
        suspected_root_cause="Provider errors correlate with the current window.",
        impact={
            "level": "critical_budget_burn",
            "slo_target": 0.99,
            "short_burn_rate": 12.0,
            "long_burn_rate": 11.0,
        },
        evidence=[
            Evidence(
                source="prometheus",
                query="sum(rate(app_llm_errors_total[5m]))",
                window="30m",
                value=0.12,
            ),
            Evidence(
                source="opensearch",
                query='resource.service.name:"product-reviews" AND body:*timeout*',
                window="30m",
                value=3,
            ),
        ],
        rca_candidates=[{"service": "product-reviews", "score": 0.83, "signals": {"metric": 1.0}}],
        runbook_id="llm-timeout-escalation",
        recommended_action="Escalate to the owning team.",
    )


def test_summary_preserves_scope_and_exact_queries():
    summary = IncidentSummaryGenerator("http://grafana/grafana", "opensearch").generate(incident())
    assert "production" in summary
    assert "tenant-42" in summary
    assert "sum(rate(app_llm_errors_total[5m]))" in summary
    assert 'resource.service.name:"product-reviews" AND body:*timeout*' in summary
    assert "critical_budget_burn" in summary
    assert '"short_burn_rate": 12.0' in summary


def test_grafana_explore_link_is_url_encoded():
    summary = IncidentSummaryGenerator("http://grafana/grafana", "opensearch").generate(incident())
    explore_line = next(line for line in summary.splitlines() if "/explore?" in line)
    assert "resource.service.name%" in explore_line
    assert '{"query":' not in explore_line
