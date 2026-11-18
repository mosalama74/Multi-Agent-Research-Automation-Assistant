from __future__ import annotations

import json

from src.models import WorkflowResult


def workflow_result_to_json(result: WorkflowResult) -> str:
    payload = {
        "run_id": result.run_id,
        "status": result.status,
        "task": result.task,
        "sources": [
            {"name": source.name, "type": source.source_type, "metadata": source.metadata}
            for source in result.sources
        ],
        "agent_outputs": result.agent_outputs,
        "actions": result.actions,
        "email_subject": result.email_subject,
        "email_body": result.email_body,
        "errors": result.errors,
        "duration_seconds": round(result.duration_seconds, 3),
    }
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str)
