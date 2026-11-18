from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from src.agents import ActionPlannerAgent, AnalysisAgent, ResearchAgent, SummarizerAgent, VerificationAgent
from src.ingestion import retrieve_sources
from src.models import SourceInput, WorkflowResult


@dataclass
class WorkflowEvent:
    name: str
    status: str
    detail: str = ""


class MultiAgentWorkflow:
    """Coordinates retrieval and five specialist agents in a traceable workflow."""

    def __init__(self, llm_client) -> None:
        self.llm = llm_client
        self.last_events: list[WorkflowEvent] = []

    def run(self, task: str, inputs: list[SourceInput]) -> WorkflowResult:
        started = time.perf_counter()
        run_id = str(uuid.uuid4())
        self.last_events = []
        outputs: dict[str, str] = {}
        errors: list[str] = []
        sources, retrieval_errors = retrieve_sources(inputs)
        errors.extend(retrieval_errors)
        self.last_events.append(WorkflowEvent("Data Retrieval Agent", "success" if sources else "failed", f"Loaded {len(sources)} source(s); {len(retrieval_errors)} retrieval error(s)."))

        if not sources:
            return WorkflowResult(
                run_id=run_id,
                status="failed",
                task=task,
                sources=[],
                agent_outputs={},
                report_markdown="# Workflow failed\n\nNo source could be retrieved. Check the input files or URLs and try again.",
                actions=["Fix the source errors and rerun the workflow."],
                email_subject="Workflow failed",
                email_body="No source could be retrieved.",
                errors=errors or ["No data sources supplied."],
                duration_seconds=time.perf_counter() - started,
            )

        research_agent = ResearchAgent(self.llm)
        analysis_agent = AnalysisAgent(self.llm)
        verification_agent = VerificationAgent(self.llm)
        summarizer_agent = SummarizerAgent(self.llm)
        planner_agent = ActionPlannerAgent(self.llm)

        try:
            outputs[research_agent.name] = research_agent.run(task, sources)
            self.last_events.append(WorkflowEvent(research_agent.name, "success", "Extracted source-grounded evidence."))

            outputs[analysis_agent.name] = analysis_agent.run(task, sources, outputs[research_agent.name])
            self.last_events.append(WorkflowEvent(analysis_agent.name, "success", "Analyzed evidence and gaps."))

            outputs[verification_agent.name] = verification_agent.run(task, sources, outputs[research_agent.name], outputs[analysis_agent.name])
            self.last_events.append(WorkflowEvent(verification_agent.name, "success", "Audited the analysis for unsupported claims."))

            outputs[summarizer_agent.name] = summarizer_agent.run(
                task, outputs[research_agent.name], outputs[analysis_agent.name], outputs[verification_agent.name]
            )
            self.last_events.append(WorkflowEvent(summarizer_agent.name, "success", "Composed the final Markdown report."))

            planned = planner_agent.run(task, outputs[summarizer_agent.name], outputs[verification_agent.name])
            outputs[planner_agent.name] = str(planned)
            self.last_events.append(WorkflowEvent(planner_agent.name, "success", "Created next steps and an email draft."))
            status = "success"
            actions = planned["actions"] or ["Review the report and choose the next action."]
            email_subject, email_body = planned["email_subject"], planned["email_body"]
            report = self._compose_report(run_id, task, sources, outputs, actions, errors)
        except Exception as exc:
            errors.append(f"Workflow stopped: {type(exc).__name__}: {exc}")
            self.last_events.append(WorkflowEvent("Workflow", "failed", str(exc)))
            status = "failed"
            actions = ["Review the error details, confirm your Groq API key/model configuration, and rerun."]
            email_subject, email_body = "AgentFlow workflow failed", "The workflow did not complete. Review the application error details."
            report = self._compose_failure_report(task, sources, outputs, errors)

        return WorkflowResult(
            run_id=run_id,
            status=status,
            task=task,
            sources=sources,
            agent_outputs=outputs,
            report_markdown=report,
            actions=actions,
            email_subject=email_subject,
            email_body=email_body,
            errors=errors,
            duration_seconds=time.perf_counter() - started,
        )

    @staticmethod
    def _compose_report(run_id: str, task: str, sources, outputs: dict[str, str], actions: list[str], errors: list[str]) -> str:
        source_lines = "\n".join(
            f"- **{source.name}** ({source.source_type}) — {source.metadata.get('rows', source.metadata.get('pages', 'metadata available'))}"
            for source in sources
        )
        action_lines = "\n".join(f"- {action}" for action in actions)
        warnings = "\n".join(f"- {error}" for error in errors) if errors else "- No source retrieval errors were recorded."
        summary = outputs.get("SummarizerAgent", "No summary was generated.")
        return (
            "# AgentFlow Research & Automation Report\n\n"
            f"**Run ID:** `{run_id}`  \
"
            f"**User task:** {task}\n\n"
            "## Data Sources\n" + source_lines + "\n\n"
            + summary + "\n\n"
            "## Recommended Actions\n" + action_lines + "\n\n"
            "## Workflow and Quality Notes\n" + warnings + "\n\n"
            "*This report is AI-generated. Validate consequential findings against the source material before acting.*\n"
        )

    @staticmethod
    def _compose_failure_report(task: str, sources, outputs: dict[str, str], errors: list[str]) -> str:
        source_lines = "\n".join(f"- {source.name} ({source.source_type})" for source in sources) or "- No sources loaded"
        error_lines = "\n".join(f"- {error}" for error in errors) or "- Unknown error"
        completed = "\n\n".join(f"### {name}\n{value}" for name, value in outputs.items()) or "No agent completed."
        return (
            "# AgentFlow Workflow Failure\n\n"
            f"**Task:** {task}\n\n## Sources\n{source_lines}\n\n"
            f"## Error Details\n{error_lines}\n\n## Partial Outputs\n{completed}\n"
        )
