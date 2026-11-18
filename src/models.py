from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SourceInput:
    """An input to the parallel retrieval stage."""

    kind: str  # file | url | sqlite
    name: str
    payload: bytes | str
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class DataSource:
    name: str
    source_type: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowResult:
    run_id: str
    status: str
    task: str
    sources: list[DataSource]
    agent_outputs: dict[str, str]
    report_markdown: str
    actions: list[str]
    email_subject: str
    email_body: str
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
