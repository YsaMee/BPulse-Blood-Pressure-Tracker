# pdf_export.py — ReportLab PDF generation for BPulse
from io import BytesIO
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, CondPageBreak, KeepTogether, PageBreak
)
from reportlab.graphics.shapes import Drawing, Line, String, PolyLine, Rect, Circle

# Usable width between 1.4 cm margins on A4 (approx 18.2 cm / 516 pt)
PAGE_MARGIN = 1.4 * cm
CONTENT_WIDTH = A4[0] - (2 * PAGE_MARGIN)

CATEGORY_HEX = {
    "Normal": "#15803D",
    "Elevated": "#92400E",
    "Stage 1 Hypertension": "#9A3412",
    "Stage 2 Hypertension": "#9F1239",
    "Crisis": "#7F1D1D",
    "Hypertensive Crisis": "#7F1D1D",
}
CATEGORY_COLORS = {k: colors.HexColor(v) for k, v in CATEGORY_HEX.items()}
CATEGORY_ORDER = [
    "Normal",
    "Elevated",
    "Stage 1 Hypertension",
    "Stage 2 Hypertension",
    "Crisis",
    "Hypertensive Crisis",
]

NOTES_MAX_CHARS = 240


def _p(text, style):
    return Paragraph(escape(str(text or "")), style)


def build_patient_pdf(person_name, person_id, records, advice=None, timeframe_label="All Records"):
    records = sorted(
        records,
        key=lambda r: (
            getattr(r, 'record_date', getattr(r, 'date', None)),
            getattr(r, 'record_time', getattr(r, 'time', None)),
        ),
    )
    safe_name = escape(str(person_name or "Patient"))

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=PAGE_MARGIN,
        rightMargin=PAGE_MARGIN,
        topMargin=PAGE_MARGIN,
        bottomMargin=PAGE_MARGIN,
        title=f"BP Report — {person_name}",
        author="BPulse",
    )

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle(
        "h1",
        parent=styles["Heading1"],
        textColor=colors.HexColor("#00507d"),
        fontSize=18,
        leading=22,
        spaceAfter=3,
    )
    h2 = ParagraphStyle(
        "h2",
        parent=styles["Heading2"],
        textColor=colors.HexColor("#131b2e"),
        fontSize=12,
        leading=15,
        spaceAfter=4,
        spaceBefore=6,
    )
    body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=9.5, leading=13)
    meta = ParagraphStyle(
        "meta",
        parent=styles["BodyText"],
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#707881"),
    )
    cell = ParagraphStyle(
        "cell",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8,
        leading=10.5,
    )
    cell_bold = ParagraphStyle(
        "cell_bold",
        parent=styles["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10.5,
    )

    story = []
    # Header Banner
    story.append(Paragraph("BPulse — Clinical Blood Pressure Report", h1))
    story.append(Paragraph(f"Patient: <b>{safe_name}</b> (ID #BP-{person_id})", body))
    story.append(Paragraph(f"Reporting Window: {timeframe_label}  |  Generated on: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", meta))
    story.append(Spacer(1, 0.25 * cm))

    if not records:
        story.append(Paragraph("No blood pressure records available for the selected timeframe.", body))
        doc.build(story)
        buffer.seek(0)
        return buffer

    total = len(records)
    avg_sys = sum(r.get_systolic() for r in records) / total
    avg_dia = sum(r.get_diastolic() for r in records) / total
    pulses = [r.get_pulse_rate() for r in records if isinstance(r.get_pulse_rate(), int)]
    avg_pulse = sum(pulses) / len(pulses) if pulses else None
    first_date = getattr(records[0], 'record_date', getattr(records[0], 'date', ''))
    last_date = getattr(records[-1], 'record_date', getattr(records[-1], 'date', ''))

    cat_counts = {}
    for r in records:
        c = r.get_bp_category()
        cat_counts[c] = cat_counts.get(c, 0) + 1
    ordered_cats = [c for c in CATEGORY_ORDER if c in cat_counts] + [c for c in cat_counts if c not in CATEGORY_ORDER]

    # ---- 1. Summary Scorecard Table ----
    story.append(Paragraph("Vitals Summary Scorecard", h2))
    summary_data = [
        ["Total Readings", str(total)],
        ["Date Range", f"{first_date} to {last_date}"],
        ["Average Blood Pressure", f"{avg_sys:.1f} / {avg_dia:.1f} mmHg (MAP: ~{int((2*avg_dia + avg_sys)/3)} mmHg)"],
        ["Average Resting Pulse", f"{avg_pulse:.1f} bpm" if avg_pulse is not None else "N/A"],
    ]
    summary_table = Table(summary_data, colWidths=[4.8 * cm, CONTENT_WIDTH - (4.8 * cm)])
    summary_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
            ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#334155")),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
            ("TOPPADDING", (0, 0), (-1, -1), 3.5),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ])
    )
    summary_table.hAlign = "LEFT"
    story.append(summary_table)
    story.append(Spacer(1, 0.25 * cm))

    # ---- 2. AHA/ACC Classification Distribution Table ----
    story.append(Paragraph("AHA/ACC Classification Distribution", h2))
    cat_rows = [[
        Paragraph("<b>Category</b>", cell),
        Paragraph("<b>Count</b>", cell),
        Paragraph("<b>Percentage</b>", cell),
        Paragraph("<b>Guideline Recommendation</b>", cell),
    ]]
    cat_guide = {
        "Normal": "Optimal range (<120/<80). Sustain balanced nutrition & activity.",
        "Elevated": "Early elevation (120-129/<80). Reduce dietary sodium.",
        "Stage 1 Hypertension": "Stage 1 HTN (130-139/80-89). Lifestyle & clinical checkup within 1 mo.",
        "Stage 2 Hypertension": "Stage 2 HTN (>=140/>=90). Clinical evaluation within 1-2 days.",
        "Crisis": "Emergency (>180/>120). Seek urgent care if symptomatic.",
        "Hypertensive Crisis": "Emergency (>180/>120). Seek urgent care if symptomatic.",
    }
    for cat in ordered_cats:
        count = cat_counts[cat]
        hex_c = CATEGORY_HEX.get(cat, "#000000")
        cat_p = Paragraph(f'<font color="{hex_c}"><b>{escape(cat)}</b></font>', cell)
        guide_p = Paragraph(escape(cat_guide.get(cat, "")), cell)
        cat_rows.append([
            cat_p,
            str(count),
            f"{(count / total) * 100:.1f}%",
            guide_p,
        ])

    rec_col_width = CONTENT_WIDTH - (4.2 * cm + 1.8 * cm + 2.4 * cm)
    cat_table = Table(cat_rows, colWidths=[4.2 * cm, 1.8 * cm, 2.4 * cm, rec_col_width])
    cat_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#00507d")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
            ("TOPPADDING", (0, 0), (-1, -1), 3.5),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ])
    )
    cat_table.hAlign = "LEFT"
    story.append(cat_table)
    story.append(Spacer(1, 0.3 * cm))

    # ---- 3. Trend Chart (Kept together with its title and sized at 130 pt to comfortably fit Page 1!) ----
    chart_title = Paragraph("Blood Pressure Trend Comparison Chart", h2)
    chart_drawing = _build_comparison_chart(records, width=CONTENT_WIDTH, height=130)
    story.append(KeepTogether([chart_title, chart_drawing]))

    # ---- 4. Detailed Chronological Readings Table on Page 2 ----
    story.append(PageBreak())
    story.append(Paragraph("Chronological Readings Log", h1))
    story.append(Paragraph(f"Patient: <b>{safe_name}</b> (ID #BP-{person_id}) &bull; Complete Log of All Readings Recorded", meta))
    story.append(Spacer(1, 0.3 * cm))

    header = [
        Paragraph("<b>#</b>", cell),
        Paragraph("<b>Date</b>", cell),
        Paragraph("<b>Time</b>", cell),
        Paragraph("<b>BP (mmHg)</b>", cell),
        Paragraph("<b>Pulse</b>", cell),
        Paragraph("<b>Category</b>", cell),
        Paragraph("<b>Notes</b>", cell),
    ]
    table_rows = [header]
    for i, r in enumerate(records, start=1):
        cat = r.get_bp_category()
        hex_color = CATEGORY_HEX.get(cat, "#000000")
        notes = (r.get_notes() or "").replace("\r", " ").replace("\n", " ")
        if len(notes) > NOTES_MAX_CHARS:
            notes = notes[: NOTES_MAX_CHARS - 3] + "..."

        d_str = str(getattr(r, 'record_date', getattr(r, 'date', '')))
        t_str = str(getattr(r, 'record_time', getattr(r, 'time', '')))[:5]

        table_rows.append([
            str(i),
            d_str,
            t_str,
            f"{r.get_systolic()}/{r.get_diastolic()}",
            str(r.get_pulse_rate()),
            Paragraph(f'<font color="{hex_color}"><b>{escape(cat)}</b></font>', cell),
            _p(notes, cell),
        ])

    notes_width = CONTENT_WIDTH - (0.9 * cm + 2.4 * cm + 1.6 * cm + 2.5 * cm + 1.5 * cm + 3.8 * cm)
    col_widths = [0.9 * cm, 2.4 * cm, 1.6 * cm, 2.5 * cm, 1.5 * cm, 3.8 * cm, notes_width]
    table = Table(table_rows, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#00507d")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
            ("TOPPADDING", (0, 0), (-1, -1), 3.5),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ])
    )
    table.hAlign = "LEFT"
    story.append(table)

    # ---- 5. Optional AI Advisor Recommendations ----
    if advice:
        story.append(Spacer(1, 0.4 * cm))
        story.append(CondPageBreak(5 * cm))
        story.append(Paragraph("AI Cardiovascular Health Advisor Recommendations", h2))
        story.append(Paragraph(f"<b>Urgency Assessment:</b> {advice.get('urgency', 'routine').upper()}", body))
        story.append(Paragraph(f"<b>Clinical Summary:</b> {escape(advice.get('summary', ''))}", body))
        if advice.get("suggestions"):
            tips_text = " | ".join(f"{s.get('title', '')}: {s.get('detail', '')}" for s in advice.get("suggestions", [])[:3])
            story.append(Paragraph(f"<b>Key Lifestyle Suggestions:</b> {escape(tips_text)}", meta))

    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph("Notice: This report is for personal monitoring only and does not replace professional medical advice, diagnosis, or clinical treatment.", meta))

    doc.build(story)
    buffer.seek(0)
    return buffer


def _build_comparison_chart(records, width=None, height=130):
    width = int(width or CONTENT_WIDTH)
    font = "Helvetica"
    grey = colors.HexColor("#64748b")
    drawing = Drawing(width, height)

    if len(records) < 2:
        drawing.add(String(10, height / 2, "Need at least 2 readings for a trend curve.", fontName=font, fontSize=9, fillColor=grey))
        return drawing

    plot_left, plot_right = 38, width - 15
    plot_bottom, plot_top = 22, height - 24

    def y_for(bp):
        bp = max(40, min(200, bp))
        return plot_bottom + ((bp - 40) / 160) * (plot_top - plot_bottom)

    # Target normal zone band (60 to 120 mmHg)
    y_120, y_80 = y_for(120), y_for(80)
    drawing.add(Rect(plot_left, y_80, plot_right - plot_left, y_120 - y_80, fillColor=colors.HexColor("#89f5e7"), fillOpacity=0.25, strokeColor=None))
    drawing.add(String(plot_right - 4, y_80 + 2, "AHA normal target (<120 / <80)", fontName=font, fontSize=6.5, textAnchor="end", fillColor=colors.HexColor("#006a61")))

    # Axes
    axis = colors.HexColor("#cbd5e1")
    drawing.add(Line(plot_left, plot_bottom, plot_right, plot_bottom, strokeColor=axis, strokeWidth=1))
    drawing.add(Line(plot_left, plot_bottom, plot_left, plot_top, strokeColor=axis, strokeWidth=1))

    # Horizontal guide ticks & labels
    for bp in (80, 120, 140, 160):
        y = y_for(bp)
        drawing.add(Line(plot_left - 3, y, plot_left, y, strokeColor=grey, strokeWidth=0.75))
        drawing.add(Line(plot_left, y, plot_right, y, strokeColor=colors.HexColor("#f1f5f9"), strokeWidth=0.5))
        drawing.add(String(plot_left - 5, y - 2.5, str(bp), fontName=font, fontSize=6.5, textAnchor="end", fillColor=grey))

    # X-axis endpoints
    first_d = str(getattr(records[0], 'record_date', getattr(records[0], 'date', '')))
    last_d = str(getattr(records[-1], 'record_date', getattr(records[-1], 'date', '')))
    drawing.add(String(plot_left, plot_bottom - 10, first_d, fontName=font, fontSize=6.5, fillColor=grey))
    drawing.add(String(plot_right, plot_bottom - 10, last_d, fontName=font, fontSize=6.5, textAnchor="end", fillColor=grey))

    n = len(records)
    sys_pts, dia_pts = [], []
    for i, r in enumerate(records):
        x = plot_left + (i * (plot_right - plot_left) / max(1, n - 1))
        sys_y = y_for(r.get_systolic())
        dia_y = y_for(r.get_diastolic())
        sys_pts.append((x, sys_y))
        dia_pts.append((x, dia_y))

    sys_color = colors.HexColor("#0284c7")
    dia_color = colors.HexColor("#0d9488")
    drawing.add(PolyLine([c for pt in sys_pts for c in pt], strokeColor=sys_color, strokeWidth=1.75))
    drawing.add(PolyLine([c for pt in dia_pts for c in pt], strokeColor=dia_color, strokeWidth=1.75))

    # Dot markers on points
    for x, y in sys_pts:
        drawing.add(Circle(x, y, 2.2, fillColor=sys_color, strokeColor=None))
    for x, y in dia_pts:
        drawing.add(Circle(x, y, 2.2, fillColor=dia_color, strokeColor=None))

    # Legend at the top
    ly = height - 12
    drawing.add(Rect(plot_left, ly, 7, 7, fillColor=sys_color, strokeColor=None))
    drawing.add(String(plot_left + 11, ly + 1, "Systolic (SYS)", fontName=font, fontSize=7.5, fillColor=sys_color))
    drawing.add(Rect(plot_left + 80, ly, 7, 7, fillColor=dia_color, strokeColor=None))
    drawing.add(String(plot_left + 91, ly + 1, "Diastolic (DIA)", fontName=font, fontSize=7.5, fillColor=dia_color))

    return drawing
