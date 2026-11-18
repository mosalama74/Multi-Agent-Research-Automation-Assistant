from src.models import DataSource, SourceInput
from src.workflow import MultiAgentWorkflow


class FakeLLMClient:
    def generate(self, agent_name, system_prompt, user_prompt, json_mode=False):
        if agent_name == "ActionPlannerAgent":
            return '{"actions": ["Review evidence", "Validate findings"], "email_subject": "Sample report", "email_body": "Please review the attached report."}'
        return f"## {agent_name}\nGenerated for tests only. [Source: sample.csv]"


def test_workflow_calls_specialists_in_order_and_returns_report(monkeypatch):
    source = DataSource(
        name="sample.csv",
        source_type="Table",
        content="Rows: 2; revenue values: 100 and 200.",
        metadata={"rows": 2, "columns": 2},
    )

    # Avoid depending on pandas/filesystem behavior in this orchestration unit test.
    monkeypatch.setattr("src.workflow.retrieve_sources", lambda inputs: ([source], []))
    workflow = MultiAgentWorkflow(FakeLLMClient())
    result = workflow.run("Summarize revenue", [SourceInput("file", "sample.csv", b"ignored")])

    assert result.status == "success"
    assert len(result.sources) == 1
    assert "Executive Summary" not in result.report_markdown  # The fake output follows agent-name headings.
    assert "SummarizerAgent" in result.report_markdown
    assert result.actions == ["Review evidence", "Validate findings"]
    assert result.email_subject == "Sample report"
    assert [event.name for event in workflow.last_events] == [
        "Data Retrieval Agent", "ResearchAgent", "AnalysisAgent", "VerificationAgent", "SummarizerAgent", "ActionPlannerAgent"
    ]
