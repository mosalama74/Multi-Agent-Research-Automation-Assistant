from __future__ import annotations

import io
import json
import os
import sqlite3
import tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable
from urllib.parse import urlparse

import pandas as pd
import requests
from pypdf import PdfReader

from src.models import DataSource, SourceInput

MAX_SOURCE_CHARS = int(os.getenv("MAX_SOURCE_CHARS", "14000"))
MAX_DOWNLOAD_BYTES = 3 * 1024 * 1024


def _truncate(text: str, limit: int = MAX_SOURCE_CHARS) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n[Content truncated at {limit:,} characters.]"


def _frame_to_text(frame: pd.DataFrame, source_name: str) -> tuple[str, dict]:
    frame = frame.copy()
    row_count, column_count = frame.shape
    details = [f"Tabular source: {source_name}", f"Rows: {row_count}; columns: {column_count}"]
    if column_count:
        details.append("Column names: " + ", ".join(map(str, frame.columns.tolist())))
    # Deterministic numeric summaries help the LLM ground its analysis in actual values.
    numeric = frame.select_dtypes(include="number")
    if not numeric.empty:
        details.append("Numeric summary (computed with pandas):")
        details.append(numeric.describe().round(3).to_string())
    details.append("Data preview:")
    details.append(frame.head(40).to_string(index=False))
    return _truncate("\n".join(details)), {
        "rows": int(row_count),
        "columns": int(column_count),
        "column_names": [str(col) for col in frame.columns.tolist()],
    }


def ingest_file(name: str, payload: bytes) -> DataSource:
    """Extract content from PDF, CSV, Excel, text, JSON, or a SQLite file."""
    extension = os.path.splitext(name.lower())[1]
    if extension == ".pdf":
        reader = PdfReader(io.BytesIO(payload))
        pages = []
        for page_number, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text() or ""
            if page_text.strip():
                pages.append(f"[Page {page_number}]\n{page_text}")
        if not pages:
            raise ValueError(f"No selectable text found in PDF '{name}'. It may be a scanned PDF; OCR is not configured in this MVP.")
        return DataSource(name, "PDF", _truncate("\n\n".join(pages)), {"pages": len(reader.pages)})

    if extension in {".csv", ".tsv"}:
        separator = "\t" if extension == ".tsv" else ","
        frame = pd.read_csv(io.BytesIO(payload), sep=separator)
        text, metadata = _frame_to_text(frame, name)
        return DataSource(name, "Table", text, metadata)

    if extension in {".xlsx", ".xls"}:
        book = pd.ExcelFile(io.BytesIO(payload))
        parts, sheet_meta = [], {}
        for sheet in book.sheet_names[:12]:
            frame = pd.read_excel(book, sheet_name=sheet)
            text, metadata = _frame_to_text(frame, f"{name} / sheet: {sheet}")
            parts.append(text)
            sheet_meta[sheet] = metadata
        return DataSource(name, "Excel workbook", _truncate("\n\n".join(parts)), {"sheets": sheet_meta})

    if extension in {".txt", ".md", ".log"}:
        return DataSource(name, "Text", _truncate(payload.decode("utf-8", errors="replace")))

    if extension == ".json":
        decoded = json.loads(payload.decode("utf-8", errors="replace"))
        return DataSource(name, "JSON", _truncate(json.dumps(decoded, indent=2, ensure_ascii=False)))

    if extension in {".db", ".sqlite", ".sqlite3"}:
        return ingest_sqlite_bytes(name, payload)

    raise ValueError(f"Unsupported file type '{extension}'. Use PDF, CSV, TSV, XLSX, TXT, JSON, or SQLite.")


def ingest_sqlite_bytes(name: str, payload: bytes) -> DataSource:
    """Read tables from a user-supplied SQLite database without modifying it."""
    # A temporary read-only database file avoids executing arbitrary SQL from the UI.
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(prefix="agentflow_", suffix=".sqlite", delete=False) as temp:
            temp.write(payload)
            temp_path = temp.name
        uri = f"{Path(temp_path).resolve().as_uri()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=5)
        try:
            tables = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
            if not tables:
                raise ValueError(f"SQLite database '{name}' does not contain user tables.")
            sections, table_meta = [], {}
            for (table_name,) in tables[:15]:
                safe_name = str(table_name).replace('"', '""')
                frame = pd.read_sql_query(f'SELECT * FROM "{safe_name}" LIMIT 100', connection)
                text, metadata = _frame_to_text(frame, f"{name} / table: {table_name}")
                sections.append(text)
                table_meta[str(table_name)] = metadata
            return DataSource(name, "SQLite database", _truncate("\n\n".join(sections)), {"tables": table_meta})
        finally:
            connection.close()
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def fetch_url(url: str, headers: dict[str, str] | None = None, name: str | None = None) -> DataSource:
    """Fetch an HTTP(S) JSON, CSV, text, or published Google Sheets export URL."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("URL must start with http:// or https://")
    response = requests.get(url, headers=headers or {}, timeout=(5, 20), stream=True)
    try:
        response.raise_for_status()
        chunks, total = [], 0
        for chunk in response.iter_content(chunk_size=65536):
            if not chunk:
                continue
            total += len(chunk)
            if total > MAX_DOWNLOAD_BYTES:
                raise ValueError(f"Response exceeded the {MAX_DOWNLOAD_BYTES // (1024 * 1024)} MB download limit.")
            chunks.append(chunk)
        payload = b"".join(chunks)
        content_type = response.headers.get("content-type", "").lower()
    finally:
        response.close()

    filename = name or parsed.netloc + (parsed.path or "/")
    if "json" in content_type or payload.lstrip().startswith((b"{", b"[")):
        try:
            decoded = json.loads(payload.decode("utf-8", errors="replace"))
            return DataSource(filename, "REST API / JSON", _truncate(json.dumps(decoded, indent=2, ensure_ascii=False)), {"url": url, "status_code": response.status_code})
        except json.JSONDecodeError:
            pass
    if "csv" in content_type or parsed.path.lower().endswith(".csv") or "export?format=csv" in url:
        try:
            frame = pd.read_csv(io.BytesIO(payload))
            text, metadata = _frame_to_text(frame, filename)
            metadata.update({"url": url, "status_code": response.status_code})
            return DataSource(filename, "REST API / CSV or Google Sheets", text, metadata)
        except Exception:
            pass
    text = payload.decode("utf-8", errors="replace")
    return DataSource(filename, "HTTP text", _truncate(text), {"url": url, "status_code": response.status_code, "content_type": content_type})


def retrieve_sources(inputs: Iterable[SourceInput]) -> tuple[list[DataSource], list[str]]:
    """Retrieve several user-selected inputs concurrently and isolate source failures."""
    specs = list(inputs)
    if not specs:
        return [], ["Add at least one file or URL before running the workflow."]

    sources: list[DataSource] = []
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(specs)))) as executor:
        future_map = {}
        for spec in specs:
            if spec.kind == "file":
                future = executor.submit(ingest_file, spec.name, bytes(spec.payload))
            elif spec.kind == "sqlite":
                future = executor.submit(ingest_sqlite_bytes, spec.name, bytes(spec.payload))
            elif spec.kind == "url":
                future = executor.submit(fetch_url, str(spec.payload), spec.headers, spec.name)
            else:
                errors.append(f"{spec.name}: unsupported source kind '{spec.kind}'.")
                continue
            future_map[future] = spec.name
        for future in as_completed(future_map):
            source_name = future_map[future]
            try:
                sources.append(future.result())
            except Exception as exc:  # Report per-source errors and keep healthy sources usable.
                errors.append(f"{source_name}: {type(exc).__name__}: {exc}")
    # Stable display order independent of network completion order.
    order = {spec.name: index for index, spec in enumerate(specs)}
    sources.sort(key=lambda source: order.get(source.name, len(order)))
    return sources, errors
