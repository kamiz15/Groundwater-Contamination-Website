"""
pdf_report.py — Professional PDF report generation for CAST.
ReportLab-based with embedded matplotlib charts and CAST branding.
"""

import io
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.graphics import renderPDF
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.svgpath import SvgPath
from reportlab.platypus import (
    CondPageBreak, HRFlowable, Image, KeepTogether, Paragraph,
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
_DFG_BLUE = colors.Color(0.000, 0.329, 0.612)
_TUE_RED = colors.Color(0.702, 0.000, 0.188)
_SOFT_BG = colors.Color(0.965, 0.975, 0.988)

# matplotlib hex equivalents
_MPL_NAVY   = "#1B3A6B"
_MPL_BLUE   = "#2E6EBD"
_MPL_TEAL   = "#0D9887"
_MPL_AMBER  = "#F59E0B"
_MPL_LIGHT  = "#EBF0F8"
_MPL_STRIPE = "#E0E8F2"

_FONT_REGULAR = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"
_FONT_ITALIC = "Helvetica-Oblique"


def _register_pdf_fonts():
    global _FONT_REGULAR, _FONT_BOLD, _FONT_ITALIC
    font_dir = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
    regular = font_dir / "DejaVuSans.ttf"
    bold = font_dir / "DejaVuSans-Bold.ttf"
    italic = font_dir / "DejaVuSans-Oblique.ttf"
    bold_italic = font_dir / "DejaVuSans-BoldOblique.ttf"
    if not (regular.exists() and bold.exists() and italic.exists() and bold_italic.exists()):
        return
    try:
        pdfmetrics.registerFont(TTFont("CASTDejaVu", str(regular)))
        pdfmetrics.registerFont(TTFont("CASTDejaVu-Bold", str(bold)))
        pdfmetrics.registerFont(TTFont("CASTDejaVu-Italic", str(italic)))
        pdfmetrics.registerFont(TTFont("CASTDejaVu-BoldItalic", str(bold_italic)))
        pdfmetrics.registerFontFamily(
            "CASTDejaVu",
            normal="CASTDejaVu",
            bold="CASTDejaVu-Bold",
            italic="CASTDejaVu-Italic",
            boldItalic="CASTDejaVu-BoldItalic",
        )
        _FONT_REGULAR = "CASTDejaVu"
        _FONT_BOLD = "CASTDejaVu-Bold"
        _FONT_ITALIC = "CASTDejaVu-Italic"
    except Exception:
        pass


_register_pdf_fonts()
PAGE_W, PAGE_H = A4
CONTENT_W = PAGE_W - 40 * mm
HEADER_H = 42 * mm
FOOTER_H = 14 * mm
BASE_DIR = Path(__file__).resolve().parent
REPORT_ASSET_DIR = BASE_DIR / "static" / "report_assets"
DFG_LOGO_PATH = REPORT_ASSET_DIR / "dfg-logo-foerderung" / "dfg_logo_schriftzug_blau_foerderung_de.png"
TUEBINGEN_LOGO_PATH = REPORT_ASSET_DIR / "Logo_Universitaet_Tuebingen.svg"


class CASTReport:
    """Professional PDF report for all CAST model types."""

    VERSION = "2.1"

    def __init__(self, title: str, model_name: str, logo_path: str = None):
        self.title = title
        self.model_name = model_name
        self.logo_path = logo_path
        self.date = datetime.now().strftime("%d %b %Y  %H:%M")
        self._build_styles()

    # ── Style definitions ──────────────────────────────────────────────────────

    def _build_styles(self):
        ss = getSampleStyleSheet()
        self.s_title = ParagraphStyle(
            "CastTitle", parent=ss["Normal"],
            fontSize=24, leading=30, fontName=_FONT_BOLD,
            textColor=_NAVY, spaceAfter=1 * mm, alignment=TA_CENTER,
        )
        self.s_subtitle = ParagraphStyle(
            "CastSubtitle", parent=ss["Normal"],
            fontSize=11, leading=15, fontName=_FONT_REGULAR,
            textColor=_GRAY, alignment=TA_CENTER, spaceAfter=0,
        )
        self.s_h2 = ParagraphStyle(
            "CastH2", parent=ss["Normal"],
            fontSize=12, leading=16, fontName=_FONT_BOLD,
            textColor=_NAVY, spaceBefore=5 * mm, spaceAfter=1 * mm,
        )
        self.s_normal = ParagraphStyle(
            "CastNormal", parent=ss["Normal"],
            fontSize=9, leading=13, fontName=_FONT_REGULAR,
            textColor=_DARK,
        )
        self.s_bold = ParagraphStyle(
            "CastBold", parent=ss["Normal"],
            fontSize=9, leading=13, fontName=_FONT_BOLD,
            textColor=_DARK,
        )
        self.s_th = ParagraphStyle(
            "CastTH", parent=ss["Normal"],
            fontSize=9, leading=13, fontName=_FONT_BOLD,
            textColor=_WHITE,
        )
        self.s_metric_label = ParagraphStyle(
            "MetricLabel", parent=ss["Normal"],
            fontSize=8, leading=11, fontName=_FONT_REGULAR,
            textColor=_GRAY,
        )
        self.s_metric_value = ParagraphStyle(
            "MetricValue", parent=ss["Normal"],
            fontSize=15, leading=19, fontName=_FONT_BOLD,
            textColor=_NAVY,
        )
        self.s_metric_unit = ParagraphStyle(
            "MetricUnit", parent=ss["Normal"],
            fontSize=9, leading=12, fontName=_FONT_REGULAR,
            textColor=_BLUE,
        )
        self.s_caption = ParagraphStyle(
            "CastCaption", parent=ss["Normal"],
            fontSize=8, leading=11, fontName=_FONT_ITALIC,
            textColor=_GRAY, alignment=TA_CENTER,
        )
        self.s_footer = ParagraphStyle(
            "CastFooter", parent=ss["Normal"],
            fontSize=7, leading=10, fontName=_FONT_ITALIC,
            textColor=_GRAY, alignment=TA_CENTER,
        )
        self.s_disclaimer = ParagraphStyle(
            "CastDisclaimer", parent=ss["Normal"],
            fontSize=7.5, leading=11, fontName=_FONT_ITALIC,
            textColor=_GRAY,
        )

    # ── Header / footer canvas callbacks ──────────────────────────────────────

    def _draw_project_mark(self, canvas, x, y):
        canvas.setFillColor(_WHITE)
        canvas.setFont(_FONT_BOLD, 13)
        canvas.drawString(x, y, "HYMCAT")
        canvas.setFont(_FONT_BOLD, 8)
        canvas.setFillColor(colors.Color(0.78, 0.88, 1.0))
        canvas.drawString(x + 24 * mm, y, "CAST")
        canvas.setFont(_FONT_REGULAR, 7)
        canvas.drawString(x, y - 3.7 * mm, "Contaminant Assessment & Source Tool")

    def _draw_image_fit(self, canvas, path: Path, x, y, max_w, max_h):
        if not path.exists():
            return False
        reader = ImageReader(str(path))
        img_w, img_h = reader.getSize()
        scale = min(max_w / img_w, max_h / img_h)
        draw_w = img_w * scale
        draw_h = img_h * scale
        canvas.drawImage(
            str(path),
            x + (max_w - draw_w) / 2,
            y + (max_h - draw_h) / 2,
            width=draw_w,
            height=draw_h,
            mask="auto",
        )
        return True

    def _load_svg_drawing(self, path: Path):
        if not path.exists():
            return None

        root = ET.parse(path).getroot()
        view_box = root.attrib.get("viewBox", "0 0 0 0").replace(",", " ").split()
        if len(view_box) != 4:
            return None
        _min_x, _min_y, width, height = [float(value) for value in view_box]
        drawing = Drawing(width, height)

        for elem in root.iter():
            if not elem.tag.endswith("path"):
                continue
            path_data = elem.attrib.get("d")
            if not path_data:
                continue
            fill = elem.attrib.get("fill", "#000000")
            fill_color = None if fill == "none" else colors.HexColor(fill)
            drawing.add(SvgPath(path_data, fillColor=fill_color, strokeColor=None, vswap=1))
        return drawing

    def _draw_svg_fit(self, canvas, path: Path, x, y, max_w, max_h):
        drawing = self._load_svg_drawing(path)
        if drawing is None:
            return False
        scale = min(max_w / drawing.width, max_h / drawing.height)
        draw_w = drawing.width * scale
        draw_h = drawing.height * scale
        canvas.saveState()
        canvas.translate(x + (max_w - draw_w) / 2, y + (max_h - draw_h) / 2)
        canvas.scale(scale, scale)
        renderPDF.draw(drawing, canvas, 0, 0)
        canvas.restoreState()
        return True

    def _header_footer(self, canvas, doc):
        canvas.saveState()
        w, h = PAGE_W, PAGE_H

        header_bottom = h - HEADER_H
        canvas.setFillColor(_WHITE)
        canvas.rect(0, header_bottom, w, HEADER_H, fill=1, stroke=0)

        self._draw_image_fit(canvas, DFG_LOGO_PATH, 20 * mm, h - 28 * mm, 76 * mm, 20 * mm)
        self._draw_svg_fit(canvas, TUEBINGEN_LOGO_PATH, 114 * mm, h - 28 * mm, 76 * mm, 20 * mm)

        canvas.setStrokeColor(_LGRAY)
        canvas.setLineWidth(0.6)
        canvas.line(18 * mm, h - 30 * mm, w - 18 * mm, h - 30 * mm)

        canvas.setFillColor(_NAVY)
        canvas.rect(0, header_bottom, w, 11 * mm, fill=1, stroke=0)
        self._draw_project_mark(canvas, 20 * mm, header_bottom + 6.6 * mm)

        canvas.setFillColor(_WHITE)
        canvas.setFont(_FONT_BOLD, 8.5)
        canvas.drawRightString(w - 20 * mm, header_bottom + 6.7 * mm, self.model_name)
        canvas.setFont(_FONT_REGULAR, 7.5)
        canvas.setFillColor(colors.Color(0.78, 0.88, 1.0))
        canvas.drawRightString(w - 20 * mm, header_bottom + 3.1 * mm, self.date)

        canvas.setStrokeColor(_TEAL)
        canvas.setLineWidth(1.1)
        canvas.line(0, header_bottom, w, header_bottom)

        canvas.setFillColor(_NAVY)
        canvas.rect(0, 0, w, FOOTER_H, fill=1, stroke=0)

        canvas.setStrokeColor(_DFG_BLUE)
        canvas.setLineWidth(1.5)
        canvas.line(0, FOOTER_H, w / 2, FOOTER_H)
        canvas.setStrokeColor(_TUE_RED)
        canvas.line(w / 2, FOOTER_H, w, FOOTER_H)

        canvas.setFont(_FONT_REGULAR, 8)
        canvas.setFillColor(colors.Color(0.7, 0.82, 1.0))
        canvas.drawCentredString(
            w / 2, 5.5 * mm,
            f"Page {doc.page}  |  HYMCAT / CAST v{self.VERSION}  |  DFG-funded research report",
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
            ],
            [
                Paragraph("<b>Project:</b>  HYMCAT / CAST", self.s_normal),
                Paragraph("<b>Institution:</b>  Eberhard Karls Universit\u00e4t T\u00fcbingen", self.s_normal),
                Paragraph("<b>Funding:</b>  DFG - Deutsche Forschungsgemeinschaft", self.s_normal),
            ]
        ]
        t = Table(cells, colWidths=[CONTENT_W / 3] * 3)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), _LIGHT),
            ("BACKGROUND", (0, 1), (-1, 1), _SOFT_BG),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, _LGRAY),
            ("LINEBELOW", (0, 1), (-1, 1), 1.5, _BLUE),
        ]))
        return t

    # ── Input parameter table ──────────────────────────────────────────────────

    @staticmethod
    def _symbol_markup(symbol):
        raw = str(symbol).strip()
        compact = raw.replace(" ", "")
        compact = compact.replace("\u03b1", "alpha_").replace("\u00ce\u00b1", "alpha_")
        compact = compact.replace("\u03b3", "gamma").replace("\u00ce\u00b3", "gamma")
        mapping = {
            "M": "<i>M</i>",
            "H": "<i>H</i>",
            "W": "<i>W</i>",
            "Sw": "<i>S</i><sub>w</sub>",
            "S_w": "<i>S</i><sub>w</sub>",
            "alpha_Tv": "&#945;<sub>Tv</sub>",
            "alpha_tv": "&#945;<sub>Tv</sub>",
            "alpha_Th": "&#945;<sub>Th</sub>",
            "alpha_th": "&#945;<sub>Th</sub>",

            "gamma": "&#947;",
            "g": "&#947;",

            "C_A": "<i>C</i><sub>A</sub>",
            "CA": "<i>C</i><sub>A</sub>",
            "C_D": "<i>C</i><sub>D</sub>",
            "CD": "<i>C</i><sub>D</sub>",
            "C_EA0": "<i>C</i><sub>EA0</sub>",
            "C_ED0": "<i>C</i><sub>ED0</sub>",
            "Cthres": "<i>C</i><sub>thres</sub>",
            "C0": "<i>C</i><sub>0</sub>",
            "Lmax": "<i>L</i><sub>max</sub>",
            "LD": "<i>L</i><sub>D</sub>",
            "DW": "<i>D</i><sub>W</sub>",
            "dx": "<i>d</i><sub>x</sub>",
        }
        return mapping.get(compact, escape(raw))

    @staticmethod
    def _metric_value_markup(value, unit):
        value_markup = f"<b>{escape(value)}</b>"
        if unit:
            unit_markup = escape(unit)
            value_markup += f'&#8201;<font color="#2E6EBD" size="8">{unit_markup}</font>'
        return value_markup

    @staticmethod
    def _fit_image_dimensions(width_px, height_px, max_height_mm):
        """Fit an image to the report width without changing its aspect ratio."""
        img_w = CONTENT_W
        img_h = img_w * (height_px / width_px)
        max_h = max_height_mm * mm
        if img_h > max_h:
            scale = max_h / img_h
            img_w *= scale
            img_h = max_h
        return img_w, img_h

    @staticmethod
    def _fmt_value(v):
        """Two-decimal formatting for every numeric value shown in the report
        (Prof's instruction). Non-numeric values pass through unchanged."""
        if isinstance(v, bool):
            return str(v)
        if isinstance(v, (int, float)):
            return f"{float(v):.2f}"
        try:
            return f"{float(v):.2f}"
        except (TypeError, ValueError):
            return str(v)

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
                Paragraph(self._symbol_markup(p["symbol"]), self.s_bold),
                Paragraph(self._fmt_value(p["value"]), self.s_bold),
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
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
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
            val_str = self._fmt_value(out["value"])
            unit_str = str(out.get("unit", "")).strip()
            cell_content = Table(
                [
                    [Paragraph(out["label"], self.s_metric_label)],
                    [Paragraph(self._metric_value_markup(val_str, unit_str), self.s_metric_value)],
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
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
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

    def _make_comparison_chart(self, plot_data: dict) -> bytes:
        def pairs(xs, ys, limit=1200):
            clean_x, clean_y = [], []
            for x, y in zip(xs or [], ys or []):
                try:
                    xf = float(x)
                    yf = float(y)
                except (TypeError, ValueError):
                    continue
                if np.isfinite(xf) and np.isfinite(yf):
                    clean_x.append(xf)
                    clean_y.append(yf)
                if len(clean_x) >= limit:
                    break
            return clean_x, clean_y

        field_x, field_y = pairs(plot_data.get("field_x"), plot_data.get("field_y"))
        manual_x, manual_y = pairs(plot_data.get("manual_x"), plot_data.get("manual_y"), limit=100)
        if not field_y and not manual_y:
            return b""

        title = plot_data.get("title", "Computed Results")
        x_label = plot_data.get("x_label", "Site Number")
        y_label = plot_data.get("y_label", "Plume Length (m)")
        field_label = plot_data.get("field_label", "Database plume length")
        manual_label = plot_data.get("manual_label", "Model plume length")

        fig, ax = plt.subplots(figsize=(8.2, 3.4), dpi=150)
        fig.patch.set_facecolor("white")
        ax.set_facecolor("#FFFFFF")

        if field_x and field_y:
            ax.scatter(field_x, field_y, s=34, color="#5598e3", label=field_label, zorder=3)
        if manual_x and manual_y:
            ax.scatter(manual_x, manual_y, s=46, color="#0e3a69", label=manual_label, zorder=4)

        all_x = [*field_x, *manual_x]
        all_y = [*field_y, *manual_y]
        min_x, max_x = min(all_x), max(all_x)
        min_y, max_y = min(all_y), max(all_y)
        x_pad = max((max_x - min_x) * 0.04, 1.0)
        y_pad = max((max_y - min_y) * 0.08, 10.0)
        ax.set_xlim(max(0, min_x - x_pad), max_x + x_pad)
        ax.set_ylim(max(0, min_y - y_pad), max_y + y_pad)

        ax.set_title(title, fontsize=10.5, fontweight="bold", color=_MPL_NAVY, loc="left", pad=8)
        ax.set_xlabel(x_label, fontsize=9, color="#4B5563", labelpad=6)
        ax.set_ylabel(y_label, fontsize=9, color="#4B5563", labelpad=8, fontstyle="italic")
        ax.grid(color="#E5E7EB", linewidth=0.7, zorder=0)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#4B5563")
        ax.spines["bottom"].set_color("#4B5563")
        ax.tick_params(colors="#4B5563", labelsize=8)
        ax.xaxis.set_minor_locator(mticker.AutoMinorLocator())
        ax.yaxis.set_minor_locator(mticker.AutoMinorLocator())
        ax.legend(loc="upper right", fontsize=8, framealpha=0.9, edgecolor="#E5E7EB")

        plt.tight_layout(pad=0.9)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        buf.seek(0)
        return buf.read()

    def _make_chart(self, plot_data: dict) -> bytes:
        if plot_data.get("type") == "comparison_scatter":
            return self._make_comparison_chart(plot_data)

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
            topMargin=50 * mm, bottomMargin=20 * mm,
            leftMargin=20 * mm, rightMargin=20 * mm,
            title=self.title,
            author="HYMCAT / CAST Platform",
        )

        story = []

        # ── Cover block ───────────────────────────────────────────────────────
        story.append(Spacer(1, 8 * mm))
        story.append(Paragraph(self.title, self.s_title))
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph("Simulation Report", self.s_subtitle))
        story.append(Spacer(1, 6 * mm))
        story.append(self._hr(color=_TEAL, thickness=1.5))
        story.append(Spacer(1, 1 * mm))
        story.append(self._metadata_banner())
        story.append(Spacer(1, 10 * mm))

        # ── Input Parameters ──────────────────────────────────────────────────
        story.append(self._section_header("Input Parameters"))
        story.append(Spacer(1, 3 * mm))
        story.append(self.build_input_table(parameters))
        story.append(Spacer(1, 10 * mm))

        # ── Computed Results ──────────────────────────────────────────────────
        story.append(KeepTogether([
            self._section_header("Computed Results"),
            Spacer(1, 3 * mm),
            self.build_results_grid(outputs),
        ]))
        story.append(Spacer(1, 3 * mm))

        # ── Results Charts ────────────────────────────────────────────────────
        image_items = []
        if plot_images:
            image_items.extend(plot_images)
        if plot_data and not image_items:
            chart_bytes = self._make_chart(plot_data)
            if chart_bytes:
                image_items.append({
                    "title": plot_data.get("title", "Computed Results"),
                    "bytes": chart_bytes,
                    "caption": plot_data.get("caption", "Computed results chart."),
                })

        if image_items:
            first_item = image_items[0]
            first_max_height = (
                float(first_item.get("max_height_mm", 105))
                if isinstance(first_item, dict)
                else 105.0
            )
            story.append(CondPageBreak((first_max_height + 20) * mm))
            story.append(self._section_header("Results Visualisation"))
            story.append(Spacer(1, 1 * mm))

            for figure_no, item in enumerate(image_items, start=1):
                max_height_mm = 105.0
                if isinstance(item, bytes):
                    title = f"Figure {figure_no}"
                    chart_bytes = item
                    caption = ""
                else:
                    title = item.get("title", f"Figure {figure_no}")
                    chart_bytes = item.get("bytes", b"")
                    caption = item.get("caption", "")
                    max_height_mm = float(item.get("max_height_mm", 105))
                if not chart_bytes:
                    continue

                try:
                    from PIL import Image as PILImage
                    pil = PILImage.open(io.BytesIO(chart_bytes))
                    img_w, img_h = self._fit_image_dimensions(
                        pil.width, pil.height, max_height_mm
                    )
                except Exception:
                    img_w = CONTENT_W
                    img_h = min(75 * mm, max_height_mm * mm)

                img = Image(io.BytesIO(chart_bytes), width=img_w, height=img_h)
                img.hAlign = "CENTER"
                story.append(KeepTogether([
                    Paragraph(f"<b>Figure {figure_no} — {title}</b>", self.s_caption),
                    Spacer(1, 1.5 * mm),
                    img,
                    Spacer(1, 1.5 * mm),
                    Paragraph(caption, self.s_caption) if caption else Spacer(1, 0),
                ]))
                story.append(Spacer(1, 4 * mm))

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
