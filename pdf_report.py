"""
pdf_report.py — Professional PDF report generation for CAST.
ReportLab-based with embedded matplotlib charts and CAST branding.
"""

import io
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable, Image, KeepTogether, Paragraph,
    SimpleDocTemplate, Spacer, Table, TableStyle,
)

# ── CAST brand palette ─────────────────────────────────────────────────────────
_NAVY    = colors.Color(0.106, 0.231, 0.420)   # #1B3A6B
_BLUE    = colors.Color(0.180, 0.431, 0.741)   # #2E6EBD
_TEAL    = colors.Color(0.051, 0.596, 0.529)   # #0D9887
_LIGHT   = colors.Color(0.922, 0.941, 0.973)   # #EBF0F8
_STRIPE  = colors.Color(0.878, 0.910, 0.950)   # #E0E8F2
_WHITE   = colors.white
_DARK    = colors.Color(0.118, 0.145, 0.196)   # #1E2532
_GRAY    = colors.Color(0.50, 0.53, 0.58)
_LGRAY   = colors.Color(0.85, 0.87, 0.90)

# matplotlib hex equivalents
_MPL_NAVY   = "#1B3A6B"
_MPL_BLUE   = "#2E6EBD"
_MPL_TEAL   = "#0D9887"
_MPL_AMBER  = "#F59E0B"
_MPL_LIGHT  = "#EBF0F8"
_MPL_STRIPE = "#E0E8F2"

PAGE_W, PAGE_H = A4
CONTENT_W = PAGE_W - 40 * mm


class CASTReport:
    """Professional PDF report for all CAST model types."""

    VERSION = "2.0"

    def __init__(self, title: str, model_name: str):
        self.title = title
        self.model_name = model_name
        self.date = datetime.now().strftime("%d %b %Y  %H:%M")
        self._build_styles()

    # ── Style definitions ──────────────────────────────────────────────────────

    def _build_styles(self):
        ss = getSampleStyleSheet()
        self.s_title = ParagraphStyle(
            "CastTitle", parent=ss["Normal"],
            fontSize=24, leading=30, fontName="Helvetica-Bold",
            textColor=_NAVY, spaceAfter=1 * mm, alignment=TA_CENTER,
        )
        self.s_subtitle = ParagraphStyle(
            "CastSubtitle", parent=ss["Normal"],
            fontSize=11, leading=15, fontName="Helvetica",
            textColor=_GRAY, alignment=TA_CENTER, spaceAfter=0,
        )
        self.s_h2 = ParagraphStyle(
            "CastH2", parent=ss["Normal"],
            fontSize=12, leading=16, fontName="Helvetica-Bold",
            textColor=_NAVY, spaceBefore=5 * mm, spaceAfter=1 * mm,
        )
        self.s_normal = ParagraphStyle(
            "CastNormal", parent=ss["Normal"],
            fontSize=9, leading=13, fontName="Helvetica",
            textColor=_DARK,
        )
        self.s_bold = ParagraphStyle(
            "CastBold", parent=ss["Normal"],
            fontSize=9, leading=13, fontName="Helvetica-Bold",
            textColor=_DARK,
        )
        self.s_th = ParagraphStyle(
            "CastTH", parent=ss["Normal"],
            fontSize=9, leading=13, fontName="Helvetica-Bold",
            textColor=_WHITE,
        )
        self.s_metric_label = ParagraphStyle(
            "MetricLabel", parent=ss["Normal"],
            fontSize=8, leading=11, fontName="Helvetica",
            textColor=_GRAY,
        )
        self.s_metric_value = ParagraphStyle(
            "MetricValue", parent=ss["Normal"],
            fontSize=15, leading=19, fontName="Helvetica-Bold",
            textColor=_NAVY,
        )
        self.s_metric_unit = ParagraphStyle(
            "MetricUnit", parent=ss["Normal"],
            fontSize=9, leading=12, fontName="Helvetica",
            textColor=_BLUE,
        )
        self.s_caption = ParagraphStyle(
            "CastCaption", parent=ss["Normal"],
            fontSize=8, leading=11, fontName="Helvetica-Oblique",
            textColor=_GRAY, alignment=TA_CENTER,
        )
        self.s_footer = ParagraphStyle(
            "CastFooter", parent=ss["Normal"],
            fontSize=7, leading=10, fontName="Helvetica-Oblique",
            textColor=_GRAY, alignment=TA_CENTER,
        )
        self.s_disclaimer = ParagraphStyle(
            "CastDisclaimer", parent=ss["Normal"],
            fontSize=7.5, leading=11, fontName="Helvetica-Oblique",
            textColor=_GRAY,
        )

    # ── Header / footer canvas callbacks ──────────────────────────────────────

    def _header_footer(self, canvas, doc):
        canvas.saveState()
        w, h = PAGE_W, PAGE_H

        # ── Top stripe (navy) ─────────────────────────────────────────────────
        canvas.setFillColor(_NAVY)
        canvas.rect(0, h - 22 * mm, w, 22 * mm, fill=1, stroke=0)

        # Left: CAST branding
        canvas.setFillColor(_WHITE)
        canvas.setFont("Helvetica-Bold", 11)
        canvas.drawString(20 * mm, h - 10 * mm, "CAST")
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.Color(0.7, 0.82, 1.0))
        canvas.drawString(20 * mm, h - 17 * mm, "Contaminant Assessment & Source Tool")

        # Right: model name + date
        canvas.setFillColor(_WHITE)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawRightString(w - 20 * mm, h - 10 * mm, self.model_name)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.Color(0.7, 0.82, 1.0))
        canvas.drawRightString(w - 20 * mm, h - 17 * mm, self.date)

        # ── Bottom bar (navy) ─────────────────────────────────────────────────
        canvas.setFillColor(_NAVY)
        canvas.rect(0, 0, w, 14 * mm, fill=1, stroke=0)

        # Thin teal accent line above bottom bar
        canvas.setStrokeColor(_TEAL)
        canvas.setLineWidth(1.5)
        canvas.line(0, 14 * mm, w, 14 * mm)

        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.Color(0.7, 0.82, 1.0))
        canvas.drawCentredString(
            w / 2, 5.5 * mm,
            f"Page {doc.page}  ·  Generated by CAST v{self.VERSION}  ·  For research and educational use only",
        )

        canvas.restoreState()

    # ── Flow helpers ───────────────────────────────────────────────────────────

    def _hr(self, color=None, thickness=0.7):
        return HRFlowable(
            width="100%", thickness=thickness,
            color=color or _BLUE,
            spaceAfter=2 * mm, spaceBefore=1 * mm,
        )

    def _section_header(self, text: str):
        """Section heading with teal left rule rendered as a table cell."""
        data = [[Paragraph(text, self.s_h2)]]
        t = Table(data, colWidths=[CONTENT_W])
        t.setStyle(TableStyle([
            ("LINEBEFOREE", (0, 0), (0, 0), 3, _TEAL),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("BACKGROUND", (0, 0), (-1, -1), colors.Color(0.96, 0.97, 0.99)),
            ("LINEBEFORE", (0, 0), (0, -1), 3.5, _TEAL),
        ]))
        return t

    # ── Metadata banner ────────────────────────────────────────────────────────

    def _metadata_banner(self) -> Table:
        cells = [
            [
                Paragraph(f"<b>Model:</b>  {self.model_name}", self.s_normal),
                Paragraph(f"<b>Generated:</b>  {self.date}", self.s_normal),
                Paragraph(f"<b>Report version:</b>  {self.VERSION}", self.s_normal),
            ]
        ]
        t = Table(cells, colWidths=[CONTENT_W / 3] * 3)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), _LIGHT),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("LINEBELOW", (0, 0), (-1, -1), 1.5, _BLUE),
        ]))
        return t

    # ── Input parameter table ──────────────────────────────────────────────────

    def build_input_table(self, parameters: list) -> Table:
        header = [
            Paragraph("Parameter", self.s_th),
            Paragraph("Symbol", self.s_th),
            Paragraph("Value", self.s_th),
            Paragraph("Unit", self.s_th),
        ]
        rows = [header]
        for p in parameters:
            rows.append([
                Paragraph(str(p["name"]), self.s_normal),
                Paragraph(str(p["symbol"]), self.s_bold),
                Paragraph(str(p["value"]), self.s_bold),
                Paragraph(str(p["unit"]), self.s_normal),
            ])

        col_w = [CONTENT_W * 0.42, CONTENT_W * 0.18, CONTENT_W * 0.22, CONTENT_W * 0.18]
        t = Table(rows, colWidths=col_w, repeatRows=1)
        style = [
            # Header
            ("BACKGROUND", (0, 0), (-1, 0), _NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), _WHITE),
            ("LINEBELOW", (0, 0), (-1, 0), 2, _TEAL),
            # Body
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_WHITE, _LIGHT]),
            ("GRID", (0, 0), (-1, -1), 0.3, _LGRAY),
            ("LINEBELOW", (0, -1), (-1, -1), 1, _BLUE),
            # Highlight symbol/value columns
            ("TEXTCOLOR", (1, 1), (2, -1), _NAVY),
        ]
        t.setStyle(TableStyle(style))
        return t

    # ── Results metrics grid ───────────────────────────────────────────────────

    def build_results_grid(self, outputs: list) -> Table:
        """Metric cards laid out in a grid — up to 3 per row."""
        MAX_COLS = 3
        n = len(outputs)
        n_cols = min(n, MAX_COLS)
        col_w = CONTENT_W / n_cols

        # Build rows of (label, value+unit) pairs in card cells
        card_rows = []
        row_cells = []
        for i, out in enumerate(outputs):
            val_str = str(out["value"])
            unit_str = str(out.get("unit", "")).strip()
            cell_content = Table(
                [
                    [Paragraph(out["label"], self.s_metric_label)],
                    [Paragraph(f"<b>{val_str}</b>", self.s_metric_value)],
                    [Paragraph(unit_str, self.s_metric_unit)],
                ],
                colWidths=[col_w - 14],
            )
            cell_content.setStyle(TableStyle([
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ]))
            row_cells.append(cell_content)
            if len(row_cells) == n_cols or i == n - 1:
                # pad to full width
                while len(row_cells) < n_cols:
                    row_cells.append(Paragraph("", self.s_normal))
                card_rows.append(row_cells)
                row_cells = []

        outer = Table(card_rows, colWidths=[col_w] * n_cols)
        style = [
            ("BACKGROUND", (0, 0), (-1, -1), _LIGHT),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("GRID", (0, 0), (-1, -1), 0.5, _LGRAY),
            ("LINEABOVE", (0, 0), (-1, 0), 3, _TEAL),
            ("LINEBELOW", (0, -1), (-1, -1), 1.5, _BLUE),
        ]
        # Highlight first cell (primary result)
        if card_rows:
            style.append(("BACKGROUND", (0, 0), (0, 0), _STRIPE))
        outer.setStyle(TableStyle(style))
        return outer

    # ── Matplotlib chart ───────────────────────────────────────────────────────

    def _make_chart(self, plot_data: dict) -> bytes:
        labels = plot_data.get("labels", [])
        values = plot_data.get("values", [])
        ylabel = plot_data.get("ylabel", "Plume Length (m)")
        chart_title = plot_data.get("title", "Computed Results")

        if not labels or not values:
            return b""

        n = len(values)
        # Adaptive figure height
        fig_h = max(2.8, 1.4 + n * 0.52)
        fig, ax = plt.subplots(figsize=(7.8, fig_h), dpi=150)
        fig.patch.set_facecolor("white")

        # Color scheme: first bar navy (primary), rest blue, highlight max
        max_v = max(values)
        bar_colors = []
        for i, v in enumerate(values):
            if n == 1:
                bar_colors.append(_MPL_NAVY)
            elif v == max_v:
                bar_colors.append(_MPL_TEAL)
            else:
                bar_colors.append(_MPL_BLUE)

        y_pos = np.arange(n)
        bars = ax.barh(y_pos, values, color=bar_colors, height=0.55,
                       zorder=3, edgecolor="white", linewidth=0.5)

        # Value labels
        for bar, v in zip(bars, values):
            offset = max_v * 0.012
            ax.text(
                v + offset,
                bar.get_y() + bar.get_height() / 2,
                f"{v:.2f} m",
                va="center", ha="left",
                fontsize=8.5, fontweight="bold",
                color=_MPL_NAVY,
            )

        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels, fontsize=9)
        ax.set_xlabel(ylabel, fontsize=9, color="#4B5563", labelpad=6)
        ax.set_title(chart_title, fontsize=11, fontweight="bold",
                     color=_MPL_NAVY, pad=10)
        ax.set_xlim(0, max_v * 1.28)
        ax.invert_yaxis()

        # Styling
        ax.set_facecolor("#F8FAFD")
        ax.grid(axis="x", color="#CBD5E1", linewidth=0.6,
                linestyle="--", zorder=0, alpha=0.8)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#CBD5E1")
        ax.spines["bottom"].set_color("#CBD5E1")
        ax.tick_params(colors="#4B5563", length=3)
        ax.xaxis.set_minor_locator(mticker.AutoMinorLocator())

        # Legend hint for teal = max
        if n > 1:
            from matplotlib.patches import Patch
            legend_elements = [
                Patch(facecolor=_MPL_TEAL, label="Maximum"),
                Patch(facecolor=_MPL_BLUE, label="Other scenarios"),
            ]
            ax.legend(handles=legend_elements, loc="lower right",
                      fontsize=8, framealpha=0.85, edgecolor="#CBD5E1")

        plt.tight_layout(pad=0.8)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150,
                    bbox_inches="tight", facecolor="white")
        plt.close(fig)
        buf.seek(0)
        return buf.read()

    # ── Main generate ──────────────────────────────────────────────────────────

    def generate(self, parameters: list, outputs: list,
                 plot_data: dict = None, plot_images: list = None) -> bytes:
        """Render the full report and return raw PDF bytes."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            topMargin=28 * mm, bottomMargin=20 * mm,
            leftMargin=20 * mm, rightMargin=20 * mm,
            title=self.title,
            author="CAST Platform",
        )

        story = []

        # ── Cover block ───────────────────────────────────────────────────────
        story.append(Spacer(1, 6 * mm))
        story.append(Paragraph(self.title, self.s_title))
        story.append(Spacer(1, 1 * mm))
        story.append(Paragraph("Simulation Report", self.s_subtitle))
        story.append(Spacer(1, 4 * mm))
        story.append(self._hr(color=_TEAL, thickness=1.5))
        story.append(Spacer(1, 1 * mm))
        story.append(self._metadata_banner())
        story.append(Spacer(1, 7 * mm))

        # ── Input Parameters ──────────────────────────────────────────────────
        story.append(self._section_header("Input Parameters"))
        story.append(Spacer(1, 2 * mm))
        story.append(self.build_input_table(parameters))
        story.append(Spacer(1, 7 * mm))

        # ── Computed Results ──────────────────────────────────────────────────
        story.append(self._section_header("Computed Results"))
        story.append(Spacer(1, 2 * mm))
        story.append(self.build_results_grid(outputs))
        story.append(Spacer(1, 7 * mm))

        # ── Results Charts ────────────────────────────────────────────────────
        image_items = []
        if plot_images:
            image_items.extend(plot_images)
        if plot_data:
            chart_bytes = self._make_chart(plot_data)
            if chart_bytes:
                image_items.append({
                    "title": plot_data.get("title", "Computed Results"),
                    "bytes": chart_bytes,
                    "caption": plot_data.get("caption", "Computed results chart."),
                })

        if image_items:
            story.append(self._section_header("Results Visualisation"))
            story.append(Spacer(1, 2 * mm))

            for figure_no, item in enumerate(image_items, start=1):
                if isinstance(item, bytes):
                    title = f"Figure {figure_no}"
                    chart_bytes = item
                    caption = ""
                else:
                    title = item.get("title", f"Figure {figure_no}")
                    chart_bytes = item.get("bytes", b"")
                    caption = item.get("caption", "")
                if not chart_bytes:
                    continue

                try:
                    from PIL import Image as PILImage
                    pil = PILImage.open(io.BytesIO(chart_bytes))
                    aspect = pil.height / pil.width
                    img_h = min(CONTENT_W * aspect, 105 * mm)
                except Exception:
                    img_h = 75 * mm

                img = Image(io.BytesIO(chart_bytes), width=CONTENT_W, height=img_h)
                img.hAlign = "CENTER"
                story.append(KeepTogether([
                    Paragraph(f"<b>Figure {figure_no} — {title}</b>", self.s_caption),
                    Spacer(1, 1.5 * mm),
                    img,
                    Spacer(1, 1.5 * mm),
                    Paragraph(caption, self.s_caption) if caption else Spacer(1, 0),
                ]))
                story.append(Spacer(1, 7 * mm))

        # ── Disclaimer ────────────────────────────────────────────────────────
        story.append(Spacer(1, 4 * mm))
        story.append(self._hr(color=_LGRAY, thickness=0.5))
        story.append(Paragraph(
            "This report was generated automatically by the CAST (Contaminant Assessment &amp; Source Tool) "
            "platform. Results are provided for research and educational purposes only and must not be used "
            "as the sole basis for remediation or regulatory decisions. Always validate model outputs against "
            "site-specific field data and consult a qualified professional.",
            self.s_disclaimer,
        ))

        doc.build(story,
                  onFirstPage=self._header_footer,
                  onLaterPages=self._header_footer)
        return buffer.getvalue()
