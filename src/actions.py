from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from html import escape
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Preformatted


def markdown_to_pdf(markdown_text: str, title: str = "AgentFlow Research Report") -> bytes:
    """Create a simple, portable PDF report from the Markdown text."""
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=title,
        author="AgentFlow Multi-Agent Assistant",
    )
    base = getSampleStyleSheet()
    title_style = ParagraphStyle("AgentFlowTitle", parent=base["Title"], fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=colors.HexColor("#1F3A5F"), alignment=TA_LEFT, spaceAfter=12)
    heading_style = ParagraphStyle("AgentFlowHeading", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=colors.HexColor("#1F3A5F"), spaceBefore=10, spaceAfter=5)
    body_style = ParagraphStyle("AgentFlowBody", parent=base["BodyText"], fontName="Helvetica", fontSize=9, leading=13, spaceAfter=5, wordWrap="CJK")
    story = [Paragraph(escape(title), title_style), Spacer(1, 3 * mm)]
    for line in markdown_text.splitlines():
        stripped = line.strip()
        if not stripped:
            story.append(Spacer(1, 2 * mm))
        elif stripped.startswith("### "):
            story.append(Paragraph(escape(stripped[4:]), base["Heading3"]))
        elif stripped.startswith("## "):
            story.append(Paragraph(escape(stripped[3:]), heading_style))
        elif stripped.startswith("# "):
            story.append(Paragraph(escape(stripped[2:]), heading_style))
        elif stripped.startswith(("- ", "* ")):
            story.append(Paragraph("&#8226;&nbsp;" + escape(stripped[2:]), body_style))
        else:
            story.append(Paragraph(escape(stripped), body_style))
    document.build(story)
    return buffer.getvalue()


def send_email(to_address: str, subject: str, body: str) -> None:
    """Send an email through SMTP. Call only after a human explicitly approves it."""
    host = os.getenv("SMTP_HOST", "").strip()
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    sender = os.getenv("SMTP_FROM", "").strip() or username
    port = int(os.getenv("SMTP_PORT", "587"))
    if not host or not sender or not username or not password:
        raise ValueError("SMTP is not fully configured. Set SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD, and SMTP_FROM in .env.")
    if "@" not in to_address or "@" not in sender:
        raise ValueError("Enter a valid recipient and sender email address.")

    message = EmailMessage()
    message["From"] = sender
    message["To"] = to_address
    message["Subject"] = subject.strip() or "AgentFlow report"
    message.set_content(body)
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=25) as server:
            server.login(username, password)
            server.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=25) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(username, password)
            server.send_message(message)
