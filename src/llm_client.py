from __future__ import annotations

import json
import os
from typing import Any


class GroqLLMClient:
    """Small wrapper around the official Groq SDK used by each specialist agent."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key or os.getenv("GROQ_API_KEY", "").strip()
        self.model = model or os.getenv("GROQ_MODEL", "openai/gpt-oss-20b").strip()
        if not self.api_key:
            raise ValueError("GROQ_API_KEY is missing. Add it to .env or enable demo mode.")
        try:
            from groq import Groq
        except ImportError as exc:
            raise RuntimeError("The 'groq' package is not installed. Run: pip install -r requirements.txt") from exc
        self._client = Groq(api_key=self.api_key, timeout=60.0, max_retries=2)

    def generate(
        self,
        agent_name: str,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = False,
    ) -> str:
        request: dict[str, Any] = {
            "model": self.model,
            "temperature": 0.2,
            "max_tokens": 1800,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if json_mode:
            request["response_format"] = {"type": "json_object"}
        try:
            result = self._client.chat.completions.create(**request)
            content = result.choices[0].message.content or ""
            if not content.strip():
                raise RuntimeError(f"{agent_name} returned an empty response.")
            return content.strip()
        except Exception as exc:
            raise RuntimeError(f"{agent_name} failed while calling Groq: {exc}") from exc


class DemoLLMClient:
    """Deterministic stand-in for presentations and tests; does not call an LLM."""

    def generate(self, agent_name: str, system_prompt: str, user_prompt: str, json_mode: bool = False) -> str:
        if agent_name == "ResearchAgent":
            return "## Retrieved Evidence\n- The workflow received source material from the selected files or URLs.\n- Source-grounded conclusions should be checked against the source previews shown in the app."
        if agent_name == "AnalysisAgent":
            return "## Analysis\n- The inputs were collected successfully.\n- Review the table summaries and source previews before relying on any conclusion.\n- No business-specific conclusion is asserted by demo mode."
        if agent_name == "VerificationAgent":
            return "## Verification Notes\n- Demo mode does not independently validate claims with a language model.\n- Treat this output as a workflow demonstration, not an AI-verified analysis."
        if agent_name == "SummarizerAgent":
            return "## Executive Summary\nThis is a demo-mode report showing the multi-agent workflow and source traceability. Configure GROQ_API_KEY to generate a real LLM summary.\n\n## Key Findings\n- Input retrieval and table summaries are available for review.\n\n## Limitations\n- Demo mode does not perform model-based analysis."
        if agent_name == "ActionPlannerAgent":
            return json.dumps({
                "actions": [
                    "Review the report against the original sources.",
                    "Configure Groq API access to enable model-generated recommendations.",
                    "Approve the email draft manually before sending."
                ],
                "email_subject": "Research workflow report (demo mode)",
                "email_body": "This report was generated in demo mode. It demonstrates the workflow only; no LLM analysis was performed. Please configure GROQ_API_KEY for production-style analysis."
            })
        return "Demo output."
