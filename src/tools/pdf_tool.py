"""PDF report generation using ReportLab."""
from __future__ import annotations

import io
import json

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def generate_session_report(session_id: str, chat_history: list[dict], query_runs: list) -> bytes:
    """Generate a PDF report for a session and its queries."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
    )

    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    title_style.textColor = colors.HexColor("#1e40af")
    
    h2_style = styles["Heading2"]
    h2_style.textColor = colors.HexColor("#3b82f6")
    
    normal_style = styles["Normal"]
    normal_style.fontSize = 11
    normal_style.leading = 14
    
    code_style = ParagraphStyle(
        "Code",
        parent=styles["Normal"],
        fontName="Courier",
        fontSize=9,
        textColor=colors.HexColor("#475569"),
        backColor=colors.HexColor("#f1f5f9"),
        borderPadding=5,
    )
    
    story = []
    
    # Title
    story.append(Paragraph("UP Police — Data Analysis Report", title_style))
    story.append(Spacer(1, 20))
    story.append(Paragraph(f"<b>Session ID:</b> {session_id}", normal_style))
    story.append(Spacer(1, 20))

    # Add query runs
    for run in query_runs:
        if not run.answer_text:
            continue
            
        story.append(Paragraph(f"<b>Q: {run.question}</b>", h2_style))
        story.append(Spacer(1, 10))
        
        story.append(Paragraph(run.answer_text, normal_style))
        story.append(Spacer(1, 10))
        
        if run.planned_sql:
            story.append(Paragraph("<b>SQL Executed:</b>", normal_style))
            # replace newlines with <br/> for ReportLab
            sql_html = run.planned_sql.replace("\n", "<br/>")
            story.append(Paragraph(sql_html, code_style))
            story.append(Spacer(1, 10))
            
        if run.follow_up_questions:
            try:
                fups = json.loads(run.follow_up_questions)
                story.append(Paragraph("<b>Suggested Follow-ups:</b>", normal_style))
                for f in fups:
                    story.append(Paragraph(f"• {f}", normal_style))
                story.append(Spacer(1, 10))
            except Exception:
                pass
                
        story.append(Spacer(1, 20))

    if not query_runs:
        story.append(Paragraph("No queries executed in this session.", normal_style))

    doc.build(story)
    return buffer.getvalue()
