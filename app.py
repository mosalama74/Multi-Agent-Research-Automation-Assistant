from __future__ import annotations

import json
import os
from urllib.parse import urlparse

import streamlit as st
from dotenv import load_dotenv

from src.actions import markdown_to_pdf, send_email
from src.llm_client import DemoLLMClient, GroqLLMClient
from src.models import SourceInput, WorkflowResult
from src.storage import RunStore
from src.workflow import MultiAgentWorkflow
from src.workflow_utils import workflow_result_to_json

load_dotenv()
st.set_page_config(page_title="AgentFlow | Multi-Agent Assistant", page_icon="🧠", layout="wide")


@st.cache_resource
def get_store() -> RunStore:
    return RunStore()


def source_label(url: str, number: int) -> str:
    parsed = urlparse(url)
    return f"URL {number}: {parsed.netloc}{parsed.path[:45]}"


def build_inputs(uploaded_files, urls: list[str], headers: dict[str, str]) -> list[SourceInput]:
    inputs: list[SourceInput] = []
    for uploaded in uploaded_files or []:
        inputs.append(SourceInput(kind="file", name=uploaded.name, payload=uploaded.getvalue()))
    for index, url in enumerate(urls, start=1):
        inputs.append(SourceInput(kind="url", name=source_label(url, index), payload=url, headers=headers))
    return inputs


def show_dashboard(store: RunStore) -> None:
    st.title("Run History & Dashboard")
    metrics = store.metrics()
    columns = st.columns(5)
    columns[0].metric("Total runs", metrics["total_runs"])
    columns[1].metric("Successful", metrics["successful_runs"])
    columns[2].metric("Success rate", f"{metrics['success_rate_pct']}%")
    columns[3].metric("Avg. duration", f"{metrics['average_duration_seconds']} s")
    columns[4].metric("Emails sent", metrics["emails_sent"])
    st.caption("Metrics are calculated from the local SQLite audit log. Email sending is recorded only after a user-triggered attempt.")
    rows = store.recent_runs(50)
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("No workflow runs have been stored yet. Run a task from the Workspace tab.")


def show_architecture() -> None:
    st.title("Architecture & Workflow")
    st.markdown(
        """
        **AgentFlow** is a multi-agent research and automation assistant. It is not a single prompt with a role label:
        each specialist has a distinct job and receives the output of earlier steps.

        ```mermaid
        flowchart TD
            A[User task + files / API URLs] --> B[Parallel Data Retrieval]
            B --> C[Research Agent]
            C --> D[Analysis Agent]
            D --> E[Verification Agent]
            E --> F[Report Summarization Agent]
            F --> G[Action Planning Agent]
            G --> H[Markdown / PDF report]
            G --> I[Email draft]
            I --> J{Human approval}
            J --> K[SMTP send + audit log]
            B --> L[SQLite run history]
            H --> L
        ```

        ### Components
        - **Data retrieval:** PDF, TXT/Markdown, CSV/TSV, Excel, JSON, SQLite database files, REST JSON/text endpoints, and published Google Sheets CSV URLs.
        - **Specialist agents:** evidence extraction, analytical reasoning, verification, executive summarization, and action planning.
        - **Automation:** report downloads plus an SMTP email action that only runs after the user clicks the send button.
        - **Persistence:** SQLite stores run summaries and attempted email actions; the dashboard reads from that store.
        - **Evaluation:** tests use a fake LLM client, so the orchestration can be checked without spending API tokens.

        ### Reliability and safety boundaries
        - Retrieval runs concurrently; individual source failures are logged while usable sources continue.
        - The verifier is an LLM-based reviewer, not a guarantee of correctness. Validate important findings against source files.
        - Email is never sent automatically. Review the recipient, subject, and body first.
        - Demo mode uses deterministic placeholders and does **not** perform LLM analysis.
        - Scanned PDFs without an embedded text layer are not OCR-processed in this MVP.
        """
    )


def render_result(result: WorkflowResult, store: RunStore, demo_mode: bool) -> None:
    st.subheader("Workflow result")
    if result.status == "success":
        st.success(f"Workflow completed in {result.duration_seconds:.1f}s · Run ID: {result.run_id}")
    else:
        st.error(f"Workflow failed · Run ID: {result.run_id}")

    st.markdown(result.report_markdown)
    download_cols = st.columns(3)
    download_cols[0].download_button(
        "Download Markdown report",
        data=result.report_markdown,
        file_name=f"agentflow_report_{result.run_id[:8]}.md",
        mime="text/markdown",
        use_container_width=True,
    )
    try:
        pdf_bytes = markdown_to_pdf(result.report_markdown)
        download_cols[1].download_button(
            "Download PDF report",
            data=pdf_bytes,
            file_name=f"agentflow_report_{result.run_id[:8]}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
    except Exception as exc:
        download_cols[1].warning(f"PDF export is unavailable: {exc}")
    download_cols[2].download_button(
        "Download run details (JSON)",
        data=workflow_result_to_json(result),
        file_name=f"agentflow_run_{result.run_id[:8]}.json",
        mime="application/json",
        use_container_width=True,
    )

    st.markdown("### Agent trace")
    workflow = st.session_state.get("workflow_instance")
    events = workflow.last_events if workflow else []
    if events:
        st.dataframe(
            [{"Step": event.name, "Status": event.status, "Details": event.detail} for event in events],
            use_container_width=True,
            hide_index=True,
        )
    else:
        for name, output in result.agent_outputs.items():
            with st.expander(name):
                st.write(output)

    with st.expander("Source previews and metadata"):
        for source in result.sources:
            st.markdown(f"**{source.name}** — {source.source_type}")
            if source.metadata:
                st.json(source.metadata)
            st.text(source.content[:3500] + ("\n[Preview truncated]" if len(source.content) > 3500 else ""))
    if result.errors:
        with st.expander(f"Warnings / errors ({len(result.errors)})"):
            for error in result.errors:
                st.warning(error)

    st.markdown("### Review and approve email")
    if demo_mode:
        st.info("Demo mode: the email draft is illustrative. Configure a Groq key for model-generated analysis.")
    st.caption("Nothing is sent until you fill in the recipient and click **Send approved email**. Confirm SMTP settings in .env first.")
    subject_key = f"email_subject_{result.run_id}"
    body_key = f"email_body_{result.run_id}"
    recipient_key = f"email_to_{result.run_id}"
    if subject_key not in st.session_state:
        st.session_state[subject_key] = result.email_subject
    if body_key not in st.session_state:
        st.session_state[body_key] = result.email_body
    if recipient_key not in st.session_state:
        st.session_state[recipient_key] = ""
    st.text_input("Recipient email", key=recipient_key, placeholder="team@example.com")
    st.text_input("Email subject", key=subject_key)
    st.text_area("Email body", key=body_key, height=220)
    if st.button("Send approved email", type="primary", disabled=(result.status != "success")):
        try:
            send_email(st.session_state[recipient_key], st.session_state[subject_key], st.session_state[body_key])
            store.log_email(result.run_id, st.session_state[recipient_key], True, "Sent after explicit user approval.")
            st.success("Email sent and recorded in the audit log.")
        except Exception as exc:
            store.log_email(result.run_id, st.session_state[recipient_key], False, str(exc))
            st.error(f"Email was not sent: {exc}")


def main() -> None:
    store = get_store()
    st.sidebar.title("🧠 AgentFlow")
    page = st.sidebar.radio("Navigation", ["Workspace", "Run history & dashboard", "Architecture & evaluation"])
    st.sidebar.caption("Multi-agent orchestration · data retrieval · human-approved automation")

    if page == "Run history & dashboard":
        show_dashboard(store)
        return
    if page == "Architecture & evaluation":
        show_architecture()
        return

    st.title("Multi-Agent Research & Automation Assistant")
    st.write("Upload files and/or provide data URLs, then ask the agent team to analyze them, create a report, and draft follow-up actions.")

    with st.sidebar:
        st.subheader("LLM configuration")
        demo_mode = st.toggle("Demo mode (no LLM API call)", value=os.getenv("DEMO_MODE", "false").lower() == "true")
        api_key = st.text_input("Groq API key", value="", type="password", help="Optional if GROQ_API_KEY is already set in your .env file.")
        model = st.text_input("Groq model", value=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"))
        st.caption("Use a model currently available to your Groq account. API keys entered here are held only for this session.")

    upload_col, url_col = st.columns([1, 1])
    with upload_col:
        st.markdown("### 1. Add documents or databases")
        uploaded_files = st.file_uploader(
            "Upload source files",
            type=["pdf", "csv", "tsv", "xlsx", "xls", "txt", "md", "log", "json", "db", "sqlite", "sqlite3"],
            accept_multiple_files=True,
            help="PDF, CSV/TSV, Excel, text, JSON, and SQLite are supported.",
        )
    with url_col:
        st.markdown("### 2. Add APIs or Google Sheets")
        raw_urls = st.text_area(
            "HTTP(S) URLs — one per line",
            placeholder="https://jsonplaceholder.typicode.com/posts/1\nhttps://docs.google.com/spreadsheets/d/YOUR_ID/export?format=csv&gid=0",
            height=120,
        )
        raw_headers = st.text_area(
            "Optional request headers as JSON",
            placeholder='{"Authorization": "Bearer YOUR_TOKEN", "Accept": "application/json"}',
            height=80,
        )
        st.caption("Private Google Sheets can be shared using a published CSV export or an API URL accessible with your request credentials.")

    st.markdown("### 3. Describe the multi-step task")
    task = st.text_area(
        "What should the agents accomplish?",
        value="Analyze the provided information, identify the most important findings and risks, summarize the evidence for a manager, and recommend next steps. Prepare an email draft, but do not send it automatically.",
        height=115,
    )
    submitted = st.button("Run multi-agent workflow", type="primary", use_container_width=True)

    if submitted:
        urls = [line.strip() for line in raw_urls.splitlines() if line.strip()]
        if not task.strip():
            st.error("Please describe the task.")
            return
        try:
            headers = json.loads(raw_headers) if raw_headers.strip() else {}
            if not isinstance(headers, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in headers.items()):
                raise ValueError("Headers must be a JSON object containing string keys and values.")
        except (json.JSONDecodeError, ValueError) as exc:
            st.error(f"Invalid request headers: {exc}")
            return
        inputs = build_inputs(uploaded_files, urls, headers)
        if not inputs:
            st.error("Upload at least one supported file or provide at least one URL.")
            return
        try:
            llm = DemoLLMClient() if demo_mode else GroqLLMClient(api_key=api_key or None, model=model or None)
            workflow = MultiAgentWorkflow(llm)
            st.session_state["workflow_instance"] = workflow
            with st.spinner("Retrieving sources and running specialist agents..."):
                result = workflow.run(task.strip(), inputs)
            store.save_run(result)
            st.session_state["latest_result"] = result
            st.session_state["latest_demo_mode"] = demo_mode
        except Exception as exc:
            st.error(f"Could not start workflow: {exc}")
            return

    result = st.session_state.get("latest_result")
    if result:
        render_result(result, store, bool(st.session_state.get("latest_demo_mode", False)))
    else:
        st.info("Start in demo mode to test the workflow without an API key, or add GROQ_API_KEY to .env to use a real LLM.")


if __name__ == "__main__":
    main()
