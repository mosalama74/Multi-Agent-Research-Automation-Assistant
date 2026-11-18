# Face-Cam Presentation Guide (4–6 minutes)

## Opening (0:00–0:30)

“Many business tasks are not a single question. Someone needs to collect information from different files or systems, analyze it, verify the important points, prepare a report, and communicate the next steps. AgentFlow demonstrates this as a coordinated workflow of specialized AI agents, with human approval before sending an email.”

## Architecture (0:30–1:30)

Show the Architecture & Evaluation page and explain:

- **Retrieval stage:** PDF, CSV/Excel, text/JSON, SQLite, and HTTP(S) data are loaded. Multiple inputs are retrieved concurrently.
- **Research Agent:** extracts source-grounded evidence.
- **Analysis Agent:** interprets findings, patterns, risks, and gaps.
- **Verification Agent:** challenges unsupported or inconsistent claims.
- **Summarizer Agent:** produces the executive report using the verified analysis.
- **Action Planner Agent:** produces actions plus an email draft.
- **Automation / storage:** the user can download the report, approve sending an email, and review the run in SQLite-backed history.

Emphasize that the agents have separate responsibilities and pass outputs to later agents; this is not one generic prompt pretending to be several agents.

## Live run (1:30–3:00)

1. Open **Workspace**.
2. Upload `sample_data/sales.csv` and `sample_data/management_brief.txt`.
3. Turn off Demo mode after confirming a working Groq API key is configured.
4. Ask: “Compare revenue and return patterns by product, flag what needs investigation, and prepare a short management update. Do not infer causes that are not present in the data.”
5. Run the workflow and show the agent trace.
6. Open source previews to connect the report back to the original records.

If the internet/API key is unavailable during recording, use Demo mode and clearly say it demonstrates orchestration only; it does not generate real model-based analysis.

## Report and automation (3:00–4:00)

- Show the executive summary, findings, limitations, and recommended next steps.
- Download Markdown or PDF, and optionally the JSON run record.
- Show the email draft. Do not send to a real distribution list during the demo. Configure SMTP and send only to a test inbox after reviewing it and clicking the explicit approval button.

## Evaluation (4:00–5:00)

Show the terminal output for:

```powershell
pytest -q
```

Explain that the tests use a fake LLM client to verify orchestration and persistence without spending tokens or sending emails. Then open **Run history & dashboard** and show recorded runs, success rate, average duration, and email action count.

## Limitations / future work (5:00–5:30)

Be transparent about the current scope:

- Image-only scanned PDFs do not use OCR.
- Google Sheets works through an accessible CSV export/API URL; a dedicated OAuth/service-account flow is future work.
- The verifier is another LLM review step, not a guarantee that every fact is correct.
- A production deployment should add authentication, tighter network controls, secret management, scheduled runs, alerting, and deeper evaluation datasets.

## Questions to prepare for

**Why multiple agents?** Separation of responsibilities makes the workflow easier to debug, evaluate, and extend. Later agents can use earlier evidence and verification notes.

**How do you reduce hallucinations?** Source-grounded prompts, explicit source names, deterministic tabular summaries, a verification pass, visible source previews, and clear limitation reporting. None of these completely eliminates hallucinations.

**What is automated?** Source retrieval, agent orchestration, report generation, run logging, and the preparation of email content. Email delivery is gated by user approval.

**How is it tested?** Unit tests cover ingestion, agent sequence, report construction, and storage using a fake LLM. Real API quality still requires a representative evaluation set with human-reviewed expected results.
