# CAST — Full Implementation Specification

**Version:** 1.0  
**Date:** 20 April 2026  
**Scope:** All workstreams from supervisor meeting, in priority order  
**Target repository:** `github.com/kamiz15/Groundwater-Contamination-Website`

---

## Table of Contents

1. [Workstream 1 — UI Layout Standardisation](#1-ui-layout-standardisation)
2. [Workstream 2 — Visualisation Cleanup](#2-visualisation-cleanup)
3. [Workstream 3 — Symbol & Naming Consistency](#3-symbol--naming-consistency)
4. [Workstream 4 — Cirpka et al. (2005) Analytical Model](#4-cirpka-et-al-2005-analytical-model)
5. [Workstream 5 — PDF Report System](#5-pdf-report-system)
6. [Workstream 6 — Database → Model Autofill](#6-database--model-autofill)
7. [Workstream 7 — Critical Bug Fixes](#7-critical-bug-fixes)
8. [Appendix A — File Change Summary](#appendix-a--file-change-summary)
9. [Appendix B — Symbol Alias Registry](#appendix-b--symbol-alias-registry)

---

## 1. UI Layout Standardisation

**Priority:** IMMEDIATE  
**Supervisor requirement:** Every model page must follow a strict three-section order and fit on one screen.

### 1.1 Mandatory Page Structure

Every model page (analytical, numerical, empirical, future AEM) must render its content in exactly this order:

```
┌─────────────────────────────────────┐
│  [1] Conceptual Model Figure (TOP)  │
├─────────────────────────────────────┤
│  [2] Input Parameters (MIDDLE)      │
├─────────────────────────────────────┤
│  [3] Output Visualisation (BOTTOM)  │
└─────────────────────────────────────┘
```

### 1.2 Current State Assessment

The existing templates (`panel_liedl3d_single.html`, `panel_numerical_single.html`, etc.) follow a pattern of:

1. Title heading
2. Optional site-loader card (DB dropdown)
3. A Panel iframe (`panel-shell` / `panel-frame`)

The Panel iframe contains the inputs and outputs together. The **conceptual model figure is missing** from all templates.

### 1.3 Changes Required

#### 1.3.1 Template Modification (all model pages)

For every model template (listed below), insert a conceptual figure section **above** the site-loader card and Panel iframe.

**Files to modify:**

| Template | Model |
|----------|-------|
| `templates/liedl_single.html` | Liedl 2D Single |
| `templates/panel_liedl_multiple.html` | Liedl 2D Multiple |
| `templates/panel_liedl3d_single.html` | Liedl 3D Single |
| `templates/panel_liedl3d_multiple.html` | Liedl 3D Multiple |
| `templates/panel_chu_single.html` | Chu Single |
| `templates/panel_chu_multiple.html` | Chu Multiple |
| `templates/ham_single.html` | Ham Single |
| `templates/panel_ham_multiple.html` | Ham Multiple |
| `templates/panel_bioscreen_single.html` | Bioscreen Single |
| `templates/panel_bioscreen_multiple.html` | Bioscreen Multiple |
| `templates/panel_numerical_single.html` | Numerical Single |
| `templates/panel_numerical_multiple.html` | Numerical Multiple |

**HTML block to insert** (immediately after the `<h2>` heading, before the site-loader `card-like` div):

```html
<div class="card-like conceptual-figure">
  <h3>Conceptual Model</h3>
  <img
    src="{{ url_for('static', filename='images/conceptual_MODEL_NAME.png') }}"
    alt="Conceptual model diagram for MODEL_NAME"
    class="conceptual-img"
    loading="lazy"
  />
</div>
```

Replace `MODEL_NAME` with the appropriate identifier (e.g., `liedl_2d`, `chu`, `numerical`).

#### 1.3.2 Static Image Directory

Create the directory `static/images/` and place the conceptual model figures there. Each model needs one figure. The supervisor will provide these. Placeholder images should be used until then.

**Required image files:**

- `static/images/conceptual_liedl_2d.png`
- `static/images/conceptual_liedl_3d.png`
- `static/images/conceptual_chu.png`
- `static/images/conceptual_ham.png`
- `static/images/conceptual_bioscreen.png`
- `static/images/conceptual_numerical.png`
- `static/images/conceptual_cirpka.png` (for new model — see Workstream 4)

#### 1.3.3 CSS Addition

Add the following to `static/styles.css`:

```css
/* ---------- Conceptual Model Figure ---------- */
.conceptual-figure {
  text-align: center;
  margin-bottom: 1rem;
}

.conceptual-figure h3 {
  font-size: 0.92rem;
  font-weight: 700;
  color: var(--brand-800);
  margin-bottom: 0.5rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.conceptual-img {
  max-width: 100%;
  max-height: 300px;
  border-radius: 8px;
  border: 1px solid var(--panel-border);
  object-fit: contain;
}

@media (max-width: 768px) {
  .conceptual-img {
    max-height: 200px;
  }
}
```

### 1.4 "Fit on One Screen" Constraint

The Panel iframes currently use `min-height: 680px`. To ensure the full page fits on a single screen when the conceptual figure is added:

- Reduce `.panel-shell` and `.panel-frame` `min-height` to `560px` (from `680px`)
- Ensure the conceptual image `max-height` stays at `300px`
- Verify on a 1080p display that the three sections (figure + inputs + output) fit without vertical scrolling of the main page

---

## 2. Visualisation Cleanup

**Priority:** IMMEDIATE  
**Supervisor requirement:** Remove unnecessary contour/line overlays from plots; ensure 300 DPI export.

### 2.1 Remove Unnecessary Overlays

**File:** `numerical_models.py`

In the `run_numerical_model` function, the current plot code uses `mm.plot_ibound()` and `mm.plot_grid()` which add visual clutter. The supervisor has stated these are not required.

**Changes:**

1. **Remove or comment out** the `mm.plot_grid()` call (the grey grid overlay).
2. **Remove or comment out** the `mm.plot_ibound()` call (the boundary overlay).
3. Keep only the `contour_array` call which draws the actual plume contour.

Current code to modify (in `run_numerical_model`):

```python
# REMOVE these two lines:
mm.plot_grid(color=".5", alpha=0.2)
mm.plot_ibound()
```

### 2.2 Increase DPI to 300

**File:** `numerical_models.py`

Current: `plt.savefig(img, format="png", bbox_inches="tight", dpi=140)`

Change to: `plt.savefig(img, format="png", bbox_inches="tight", dpi=300)`

### 2.3 Plot Function Cleanup

**File:** `plot_functions.py`

Review all Bokeh scatter and bar plots. For any reference data lines or overlays that are not:

- the user's computed result, OR
- the database reference comparison

remove or hide them by default. The principle is: only show data that serves a direct interpretive purpose.

---

## 3. Symbol & Naming Consistency

**Priority:** IMMEDIATE  
**Supervisor requirement:** Symbols in the conceptual model, input boxes, and database must be aligned. Create an alias mapping layer if mismatches exist.

### 3.1 Current Mismatches Identified

The codebase has multiple naming conventions across layers:

| Concept | Database Column | UI Label (Panel widget) | Model Variable | Conceptual Symbol |
|---------|----------------|------------------------|----------------|-------------------|
| Aquifer thickness | `aquifer_thickness` | `M` (Liedl), `H` (Bioscreen), `A_T` (Numerical) | `M`, `Ly`, `A_T` | M |
| Source width | `plume_width` | `W` (Chu), `sourceWidthW` (Bioscreen) | `W`, `Sw` | S_w |
| Transverse dispersivity (vertical) | `hydraulic_conductivity` (**WRONG**) | `alpha_Tv`, `av` | `alpha_Tv`, `av` | α_Tv |
| Transverse dispersivity (horizontal) | — (not in DB) | `alpha_Th` | `alpha_Th` | α_Th |
| Electron donor concentration | `electron_donor` | `C_ED0`, `Cd`, `c0` | `C_ED0`, `cd` | C_D |
| Electron acceptor concentration | `electron_acceptor_o2` | `C_EA0`, `Ca` | `C_EA0`, `ca` | C_A |
| Stoichiometric ratio | — (not in DB) | `gamma`, `g` | `gamma` | γ |

**Critical problem:** `analytical_routes.py` maps `hydraulic_conductivity` → `alpha_Tv`, `alpha_Th`, `alpha`, `alpha_T`, `v`. This is **scientifically incorrect** — hydraulic conductivity (K) is not the same as transverse dispersivity (α_T).

### 3.2 Solution: Central Alias Registry

**New file to create:** `symbol_registry.py`

This file serves as the single source of truth for all symbol mappings across the application.

```python
"""
symbol_registry.py
Central alias registry for parameter name mapping across
database columns, UI labels, and model function arguments.

RULE: Conceptual Model Symbol == UI Label == Variable Name (or mapped alias)
"""

# Canonical symbols used in conceptual figures and equations.
# Each entry: canonical_symbol → { "db": column_name, "ui": widget_label, "unit": unit_string }

SYMBOL_REGISTRY = {
    # --- Geometric parameters ---
    "M": {
        "db": "aquifer_thickness",
        "ui": "Aquifer Thickness M [m]",
        "unit": "m",
        "models": ["liedl", "liedl3d", "ham", "maier"],
    },
    "S_w": {
        "db": "plume_width",
        "ui": "Source Width Sw [m]",
        "unit": "m",
        "models": ["chu", "cirpka", "numerical"],
    },
    "S_T": {
        "db": None,  # not in DB
        "ui": "Source Thickness ST [m]",
        "unit": "m",
        "models": ["numerical"],
    },
    "S_Ta": {
        "db": None,
        "ui": "Buffer Above STa [m]",
        "unit": "m",
        "models": ["numerical"],
    },
    "S_Tb": {
        "db": None,
        "ui": "Buffer Below STb [m]",
        "unit": "m",
        "models": ["numerical"],
    },

    # --- Transport parameters ---
    "alpha_Tv": {
        "db": None,  # NOT hydraulic_conductivity
        "ui": "Transverse Dispersivity αTv [m]",
        "unit": "m",
        "models": ["liedl", "liedl3d", "numerical"],
    },
    "alpha_Th": {
        "db": None,
        "ui": "Horizontal Transverse Dispersivity αTh [m]",
        "unit": "m",
        "models": ["chu", "liedl3d", "cirpka"],
    },
    "K": {
        "db": "hydraulic_conductivity",
        "ui": "Hydraulic Conductivity K [m/s]",
        "unit": "m/s",
        "models": ["numerical"],
    },

    # --- Concentration parameters ---
    "C_D": {
        "db": "electron_donor",
        "ui": "Electron Donor CD [mg/L]",
        "unit": "mg/L",
        "models": ["liedl", "liedl3d", "chu", "ham", "cirpka", "numerical"],
    },
    "C_A": {
        "db": "electron_acceptor_o2",
        "ui": "Electron Acceptor CA [mg/L]",
        "unit": "mg/L",
        "models": ["liedl", "liedl3d", "chu", "ham", "cirpka", "numerical"],
    },

    # --- Stoichiometric / reaction ---
    "gamma": {
        "db": None,
        "ui": "Stoichiometric Ratio γ [-]",
        "unit": "-",
        "models": ["liedl", "liedl3d", "chu", "ham", "cirpka", "numerical"],
    },
}


def db_to_model(db_row: dict, model_name: str) -> dict:
    """
    Map a database site row to model input parameters,
    returning only fields relevant to the given model.
    
    Returns dict of { canonical_symbol: value } for non-None values.
    """
    result = {}
    for symbol, meta in SYMBOL_REGISTRY.items():
        if model_name not in meta["models"]:
            continue
        db_col = meta.get("db")
        if db_col is None:
            continue
        value = db_row.get(db_col)
        if value is not None:
            result[symbol] = value
    return result


def get_ui_label(symbol: str) -> str:
    """Return the UI-facing label for a canonical symbol."""
    entry = SYMBOL_REGISTRY.get(symbol)
    return entry["ui"] if entry else symbol


def get_unit(symbol: str) -> str:
    """Return the unit string for a canonical symbol."""
    entry = SYMBOL_REGISTRY.get(symbol)
    return entry["unit"] if entry else ""
```

### 3.3 Fix Incorrect Mappings in Route Files

**File:** `analytical_routes.py` — in `_build_panel_query(path, site)`

**Remove** the following incorrect mapping (lines that map `hydraulic_conductivity` to dispersivity):

```python
# REMOVE — hydraulic conductivity ≠ transverse dispersivity
if conductivity is not None:
    query["alpha_Tv"] = conductivity
    query["alpha_Th"] = conductivity
    query["alpha"] = conductivity
    query["alpha_T"] = conductivity
    query["v"] = conductivity
```

**Replace with:**

```python
if conductivity is not None:
    query["hk"] = conductivity  # pass as hydraulic conductivity only
# NOTE: alpha_Tv and alpha_Th must come from user input, not from DB
```

### 3.4 Rename Panel Widget Labels

Across all Panel app files (`panel_liedl_single.py`, `panel_chu_single.py`, etc.), update widget `name` attributes to match the canonical UI labels from the Symbol Registry. Example:

- `name="Cd"` → `name="Electron Donor CD [mg/L]"`
- `name="Ca"` → `name="Electron Acceptor CA [mg/L]"`
- `name="av"` → `name="Transverse Dispersivity αTv [m]"`

This ensures what the user sees matches the conceptual figure labels.

---

## 4. Cirpka et al. (2005) Analytical Model

**Priority:** PHASE 1 (IMMEDIATE)  
**Supervisor requirement:** Non-optional. New model page required.

### 4.1 Model Mathematics

The Cirpka et al. (2005) model computes the maximum steady-state plume length for a horizontally spreading contaminant plume.

**Core equations:**

```
c_f = C_A / (γ · C_D + C_A)

L_max = S_w² / (16 · α_Th · [erfcinv(c_f)]²)

L_D = 1.5 × L_max
```

Where:
- `S_w` = source width [m]
- `α_Th` = horizontal transverse dispersivity [m]
- `C_A` = electron acceptor concentration [mg/L]
- `C_D` = electron donor concentration [mg/L]
- `γ` = stoichiometric ratio [-]
- `erfcinv` = inverse complementary error function
- `L_D` = domain length [m]

### 4.2 Backend Implementation

**File to modify:** `analytical_models.py`

Add the following at the end of the file (after the Ham section):

```python
# -------------------------
# CIRPKA et al. (2005)
# -------------------------

from scipy.special import erfcinv


def cirpka_lmax(Sw: float, alpha_Th: float, gamma: float, C_A: float, C_D: float) -> float:
    """Compute maximum plume length using Cirpka et al. (2005)."""
    if alpha_Th <= 0:
        raise ValueError("alpha_Th must be positive")
    if C_A <= 0:
        raise ValueError("C_A must be positive")
    if (gamma * C_D + C_A) <= 0:
        raise ValueError("gamma * C_D + C_A must be positive")

    cf = C_A / (gamma * C_D + C_A)
    lmax = (Sw ** 2) / (16.0 * alpha_Th * erfcinv(cf) ** 2)
    return float(lmax)


def cirpka_domain_length(lmax: float) -> float:
    """Domain length = 1.5 × L_max."""
    return 1.5 * lmax


def compute_cirpka_multiple(entries):
    """Batch compute for multiple parameter sets."""
    results = []
    for row in entries:
        Sw, alpha_Th, gamma, C_A, C_D = row
        lmax = cirpka_lmax(Sw, alpha_Th, gamma, C_A, C_D)
        results.append({"Lmax": lmax, "LD": cirpka_domain_length(lmax)})
    return results
```

### 4.3 Route Registration

**File to modify:** `analytical_routes.py`

Add two new route functions (single and multiple), following the existing pattern:

```python
# ---------- CIRPKA ----------
@analytical_bp.route("/cirpka/single")
def cirpka_single():
    sites, selected_site = _selected_site()
    return render_template(
        "panel_cirpka_single.html",
        panel_src=_panel_src("panel_cirpka_single", selected_site),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
    )


@analytical_bp.route("/cirpka/multiple")
def cirpka_multiple():
    sites, selected_site = _selected_site()
    return render_template(
        "panel_cirpka_multiple.html",
        panel_src=_panel_src("panel_cirpka_multiple", selected_site),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
    )
```

### 4.4 Panel App — Single Simulation

**New file:** `panel_cirpka_single.py`

Follow the same structure as `panel_numerical_single.py`. The Panel app needs:

**Input widgets:**

| Widget | Type | Default | Canonical Symbol |
|--------|------|---------|-----------------|
| Source Width Sw [m] | FloatInput | 10.0 | S_w |
| Horizontal Transverse Dispersivity αTh [m] | FloatInput | 0.01 | α_Th |
| Electron Acceptor CA [mg/L] | FloatInput | 8.0 | C_A |
| Electron Donor CD [mg/L] | FloatInput | 5.0 | C_D |
| Stoichiometric Ratio γ [-] | FloatInput | 3.5 | γ |

**Output display:**

- Result card showing `L_max` and `L_D` values (same card styling as numerical model)
- A scatter plot comparing the user's computed `L_max` against the database reference plume lengths (reuse the pattern from `create_liedl_scatter` in `plot_functions.py`, adapted for Cirpka)

**Callback logic:**

```python
def _run(_=None):
    try:
        lmax = cirpka_lmax(sw.value, alpha_th.value, gamma.value, ca.value, cd.value)
        ld = cirpka_domain_length(lmax)
        # Update result card with Lmax and LD
        # Update scatter plot
    except Exception as e:
        # Show error card
```

### 4.5 Panel App — Multiple Simulation

**New file:** `panel_cirpka_multiple.py`

Follow the `panel_numerical_multiple.py` Tabulator pattern:

- Tabulator widget with columns: `Sw`, `alpha_Th`, `gamma`, `C_A`, `C_D`
- "Run" button that computes `L_max` and `L_D` for each row
- Results displayed in a bar chart and/or table

### 4.6 Templates

**New file:** `templates/panel_cirpka_single.html`

Copy the structure from `templates/panel_liedl3d_single.html` and update:

- Title: "Cirpka et al. (2005) — Single Simulation"
- Panel src path: `panel_cirpka_single`
- Include conceptual figure block (per Workstream 1)

**New file:** `templates/panel_cirpka_multiple.html`

Same approach for the multiple simulation page.

### 4.7 Navigation Update

**File:** `templates/base.html`

In the "Analytical Model" dropdown menu, add two new entries after the BIOSCREEN items:

```html
<li><a class="dd-link" href="{{ url_for('analytical_bp.cirpka_single') }}">Cirpka et al. (2005) - Single</a></li>
<li><a class="dd-link" href="{{ url_for('analytical_bp.cirpka_multiple') }}">Cirpka et al. (2005) - Multiple</a></li>
```

### 4.8 Landing Page Update

**File:** `templates/analytical_landing.html`

Add a new tile for Cirpka:

```html
<div class="tile" style="padding: 18px; display:flex; flex-direction:column; justify-content:center; align-items:center; text-align:center;">
  <h3>Cirpka et al.</h3>
  <div style="display:flex; gap:12px; margin-top:12px; justify-content:center; align-items:center;">
    <a class="primary-btn" href="{{ url_for('analytical_bp.cirpka_single') }}">Single Simulation</a>
    <a class="ghost-btn" href="{{ url_for('analytical_bp.cirpka_multiple') }}">Multiple Simulation</a>
  </div>
</div>
```

### 4.9 Integration with Numerical Model

The Cirpka `L_max` is already being used inside `panel_numerical_single.py` and `panel_numerical_multiple.py` to compute `L_D = 1.5 * analytical_lmax`. Currently this uses `liedl_lmax`. The supervisor wants the option to use Cirpka instead.

**Future change** (Phase 3): Add a dropdown in the numerical model Panel apps allowing the user to select which analytical model drives the domain sizing: Liedl or Cirpka.

---

## 5. PDF Report System

**Priority:** PHASE 1  
**Supervisor requirement:** Major deliverable. Each model run must be exportable as a PDF.

### 5.1 Report Structure (Mandatory)

Each PDF report must contain:

```
┌─────────────────────────────────┐
│ HEADER                          │
│  • Tool name (e.g., "CAST")    │
│  • Date of generation          │
│  • Optional logo               │
│  • Page number                 │
├─────────────────────────────────┤
│ SECTION 1: Input Parameters     │
│  Table: Parameter | Symbol |    │
│         Value | Unit            │
├─────────────────────────────────┤
│ SECTION 2: Numerical Outputs    │
│  • L_max                       │
│  • L_D                         │
│  • Other computed values        │
├─────────────────────────────────┤
│ SECTION 3: Graph                │
│  • Plume visualisation          │
│  • Result plot                  │
└─────────────────────────────────┘
```

**Explicit exclusion:** The conceptual model figure must NOT appear in the PDF report.

### 5.2 Template Types Required

Four template layouts, each adapted for the data complexity of its model type:

| Template | Used By | Input Complexity |
|----------|---------|-----------------|
| `data_report` | Site database exports | Tabular, multi-site |
| `analytical_report` | Liedl, Chu, Ham, Cirpka, Bioscreen | 3–8 parameters, 1–2 outputs |
| `numerical_report` | Numerical model | 12+ parameters, plume plot |
| `aem_report` | Future AEM models | TBD — placeholder template |

### 5.3 Technical Implementation

**Recommended approach:** ReportLab (already Python-native, no external dependencies).

**New file:** `pdf_report.py`

```python
"""
pdf_report.py
PDF report generation for all CAST model types.
Uses ReportLab for direct PDF creation.
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from datetime import datetime
import io


class CASTReport:
    """Base report class with common header/footer and structure."""
    
    def __init__(self, title: str, model_name: str):
        self.title = title
        self.model_name = model_name
        self.date = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.styles = getSampleStyleSheet()
    
    def _header_footer(self, canvas, doc):
        """Draw header and footer on every page."""
        canvas.saveState()
        # Header
        canvas.setFont("Helvetica-Bold", 10)
        canvas.drawString(20 * mm, A4[1] - 15 * mm, f"CAST — {self.model_name}")
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(A4[0] - 20 * mm, A4[1] - 15 * mm, self.date)
        canvas.line(20 * mm, A4[1] - 18 * mm, A4[0] - 20 * mm, A4[1] - 18 * mm)
        # Footer
        canvas.setFont("Helvetica", 8)
        canvas.drawCentredString(A4[0] / 2, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()
    
    def build_input_table(self, parameters: list[dict]) -> Table:
        """
        Build input parameter table.
        parameters: list of {"symbol": str, "name": str, "value": any, "unit": str}
        """
        data = [["Parameter", "Symbol", "Value", "Unit"]]
        for p in parameters:
            data.append([p["name"], p["symbol"], str(p["value"]), p["unit"]])
        
        table = Table(data, colWidths=[60 * mm, 30 * mm, 40 * mm, 25 * mm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.18, 0.27, 0.42)),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.Color(0.95, 0.97, 1.0)]),
        ]))
        return table
    
    def build_output_section(self, outputs: list[dict]) -> list:
        """
        Build output values section.
        outputs: list of {"label": str, "value": any, "unit": str}
        """
        elements = []
        for out in outputs:
            text = f"<b>{out['label']}:</b> {out['value']} {out['unit']}"
            elements.append(Paragraph(text, self.styles["Normal"]))
            elements.append(Spacer(1, 3 * mm))
        return elements
    
    def generate(self, parameters: list, outputs: list, plot_image_bytes: bytes = None) -> bytes:
        """
        Generate the full PDF report and return as bytes.
        """
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4,
                                topMargin=25 * mm, bottomMargin=20 * mm,
                                leftMargin=20 * mm, rightMargin=20 * mm)
        
        story = []
        
        # Title
        story.append(Paragraph(f"<b>{self.title}</b>", self.styles["Title"]))
        story.append(Spacer(1, 5 * mm))
        
        # Section 1: Inputs
        story.append(Paragraph("<b>Input Parameters</b>", self.styles["Heading2"]))
        story.append(Spacer(1, 3 * mm))
        story.append(self.build_input_table(parameters))
        story.append(Spacer(1, 8 * mm))
        
        # Section 2: Outputs
        story.append(Paragraph("<b>Computed Results</b>", self.styles["Heading2"]))
        story.append(Spacer(1, 3 * mm))
        story.extend(self.build_output_section(outputs))
        story.append(Spacer(1, 8 * mm))
        
        # Section 3: Graph
        if plot_image_bytes:
            story.append(Paragraph("<b>Visualisation</b>", self.styles["Heading2"]))
            story.append(Spacer(1, 3 * mm))
            img = Image(io.BytesIO(plot_image_bytes), width=160 * mm, height=100 * mm)
            story.append(img)
        
        doc.build(story, onFirstPage=self._header_footer, onLaterPages=self._header_footer)
        return buffer.getvalue()
```

### 5.4 Adding ReportLab to Dependencies

**File:** `requirements.txt`

Add: `reportlab>=4.0,<5.0`

### 5.5 Export Route

**File to modify:** `analytical_routes.py` (and `numerical_routes.py`)

Add an export endpoint for each model. Example for Cirpka:

```python
from flask import Response
from pdf_report import CASTReport

@analytical_bp.route("/cirpka/single/export", methods=["POST"])
def cirpka_export():
    # Parse form data from the Panel app (posted via JS)
    sw = float(request.form["Sw"])
    alpha_th = float(request.form["alpha_Th"])
    gamma = float(request.form["gamma"])
    ca = float(request.form["C_A"])
    cd = float(request.form["C_D"])
    
    lmax = cirpka_lmax(sw, alpha_th, gamma, ca, cd)
    ld = cirpka_domain_length(lmax)
    
    report = CASTReport("Cirpka et al. (2005) — Single Simulation", "Cirpka Analytical")
    pdf_bytes = report.generate(
        parameters=[
            {"symbol": "Sw", "name": "Source Width", "value": sw, "unit": "m"},
            {"symbol": "αTh", "name": "Horiz. Trans. Dispersivity", "value": alpha_th, "unit": "m"},
            {"symbol": "γ", "name": "Stoichiometric Ratio", "value": gamma, "unit": "-"},
            {"symbol": "CA", "name": "Electron Acceptor", "value": ca, "unit": "mg/L"},
            {"symbol": "CD", "name": "Electron Donor", "value": cd, "unit": "mg/L"},
        ],
        outputs=[
            {"label": "Maximum Plume Length (Lmax)", "value": f"{lmax:.2f}", "unit": "m"},
            {"label": "Domain Length (LD)", "value": f"{ld:.2f}", "unit": "m"},
        ],
        plot_image_bytes=None,  # attach plot bytes when available
    )
    
    return Response(pdf_bytes, mimetype="application/pdf",
                    headers={"Content-Disposition": "attachment; filename=cirpka_report.pdf"})
```

### 5.6 UI Export Button

Each Panel app needs an "Export PDF" button that posts the current parameter values to the export endpoint. Add to each Panel app file:

```python
export_btn = pn.widgets.Button(name="Export PDF Report", button_type="default", sizing_mode="stretch_width")

def _export(_=None):
    # Trigger a JS-based form POST to the export endpoint
    # (Panel can use pn.pane.HTML with a hidden form + JS)
    pass

export_btn.on_click(_export)
```

The exact JS mechanism for triggering the download from within a Panel iframe will depend on your deployment; the simplest approach is a hidden `<form>` that posts to the Flask export route.

---

## 6. Database → Model Autofill

**Priority:** PHASE 2  
**Supervisor requirement:** When a site is selected from the dropdown, auto-fill input fields from the database.

### 6.1 Current State

This feature **partially exists**. The `_build_panel_query` functions in `analytical_routes.py`, `numerical_routes.py`, and `empirical_routes.py` already map database columns to Panel query parameters. The values are passed via URL query string to the Panel iframe, and Panel widgets read them via `pn.state.location.search`.

### 6.2 What Needs to Change

1. **Fix incorrect mappings** (covered in Workstream 3 — remove `hydraulic_conductivity` → `alpha_Tv` mapping).
2. **Use the Symbol Registry** (`symbol_registry.py` from Workstream 3) in all route files instead of ad-hoc mapping.
3. **Clearly indicate partial fill** — when the database does not contain all required fields, the UI must visually indicate which fields were auto-filled vs. which require manual entry.

### 6.3 Partial Fill Indication

In each Panel app, after reading query params, add a visual indicator:

```python
def _is_from_db(param_name: str) -> bool:
    """Check if a parameter was provided via DB (query string)."""
    return pn.state.location and param_name in pn.state.location.search

# When building widgets, add a suffix or tooltip:
sw_label = "Source Width Sw [m]"
if _is_from_db("Sw"):
    sw_label += " (from DB)"
```

### 6.4 Constraints to Document

The database schema (`sites` table) currently stores:

- `aquifer_thickness`, `plume_length`, `plume_width`, `hydraulic_conductivity`, `electron_donor`, `electron_acceptor_o2`, `electron_acceptor_no3`

Parameters NOT in the database that must always be manual input:

- Transverse dispersivities (`alpha_Tv`, `alpha_Th`)
- Porosity (`prsity`)
- Longitudinal dispersivity (`al`)
- Stoichiometric ratio (`gamma`)
- Grid spacings (`delta_x`, `delta_z`)
- Hydraulic heads (`h1`, `h2`)
- Source thickness zones (`S_T`, `S_Ta`, `S_Tb`)
- Retardation factor, decay coefficients (Bioscreen-specific)

---

## 7. Critical Bug Fixes

**Priority:** IMMEDIATE (before other work)  
**Previously identified in test case review.**

### 7.1 Bug: `load_user` Always Returns `None`

**File:** `app.py`

**Current code:**

```python
@login_manager.user_loader
def load_user(user_id):
    """
    TODO: replace with real lookup from DB.
    Right now just returns None so users are always 'not logged in'.
    """
    return None
```

**Impact:** Flask-Login is completely broken. Any `@login_required` decorators will always redirect. Even though the app currently uses `session` directly for auth, this should be fixed.

**Fix specification:**

1. Create a `User` class that implements Flask-Login's `UserMixin`
2. Implement `load_user` to query the `users` table by ID

```python
from flask_login import UserMixin

class User(UserMixin):
    def __init__(self, id, username, email):
        self.id = id
        self.username = username
        self.email = email

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, username, email FROM users WHERE id = %s", (user_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    if row:
        return User(row["id"], row["username"], row["email"])
    return None
```

### 7.2 Bug: `ensure_schema` Called on Every Connection

**File:** `data_queries.py`

**Current code:**

```python
def get_db_connection():
    connection = mysql.connector.connect(...)
    ensure_schema(connection)  # ← called EVERY time
    return connection
```

**Impact:** Schema creation statements (`CREATE TABLE IF NOT EXISTS`) execute on every single database query. This is wasteful and could cause issues under load.

**Fix specification:**

1. Add a module-level flag to track whether schema has been initialised
2. Only call `ensure_schema` on the first connection

```python
_schema_initialized = False

def get_db_connection():
    global _schema_initialized
    connection = mysql.connector.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER,
        password=DB_PASSWORD, database=DB_NAME,
    )
    if not _schema_initialized:
        ensure_schema(connection)
        _schema_initialized = True
    return connection
```

Alternatively, call `ensure_schema` once at application startup in `app.py`.

---

## Appendix A — File Change Summary

| File | Action | Workstream |
|------|--------|-----------|
| `app.py` | Fix `load_user`, add `User` class | 7 |
| `data_queries.py` | Fix `ensure_schema` call pattern | 7 |
| `analytical_models.py` | Add `cirpka_lmax`, `cirpka_domain_length`, `compute_cirpka_multiple` | 4 |
| `analytical_routes.py` | Add Cirpka routes, fix DB→model mappings, add export endpoint | 3, 4, 5 |
| `numerical_routes.py` | Fix DB→model mappings, add export endpoint | 3, 5 |
| `empirical_routes.py` | Fix DB→model mappings | 3 |
| `numerical_models.py` | Remove plot clutter, increase DPI to 300 | 2 |
| `plot_functions.py` | Review and clean up unnecessary overlays | 2 |
| `symbol_registry.py` | **NEW** — central alias mapping | 3 |
| `pdf_report.py` | **NEW** — PDF generation engine | 5 |
| `panel_cirpka_single.py` | **NEW** — Cirpka single Panel app | 4 |
| `panel_cirpka_multiple.py` | **NEW** — Cirpka multiple Panel app | 4 |
| `templates/panel_cirpka_single.html` | **NEW** — Cirpka single template | 4 |
| `templates/panel_cirpka_multiple.html` | **NEW** — Cirpka multiple template | 4 |
| `templates/base.html` | Add Cirpka to nav dropdown | 4 |
| `templates/analytical_landing.html` | Add Cirpka tile | 4 |
| All model templates (12 files) | Add conceptual figure block | 1 |
| `static/styles.css` | Add `.conceptual-figure` / `.conceptual-img` styles, reduce iframe height | 1 |
| `static/images/` | **NEW directory** — conceptual model PNGs | 1 |
| `requirements.txt` | Add `reportlab>=4.0,<5.0` | 5 |

---

## Appendix B — Symbol Alias Registry

Complete mapping of all symbols used across the system:

| Canonical | Conceptual Figure | UI Widget Label | DB Column | Model Arg (Liedl) | Model Arg (Chu) | Model Arg (Cirpka) | Model Arg (Numerical) |
|-----------|------------------|-----------------|-----------|-------------------|-----------------|--------------------|-----------------------|
| M | M | Aquifer Thickness M [m] | `aquifer_thickness` | `M` | — | — | `Ly` (derived as A_T) |
| S_w | S_w | Source Width Sw [m] | `plume_width` | — | `W` | `Sw` | — |
| S_T | S_T | Source Thickness ST [m] | — | — | — | — | `S_T` |
| α_Tv | α_Tv | Trans. Dispersivity αTv [m] | — | `alpha_Tv` | — | — | `av` |
| α_Th | α_Th | Horiz. Trans. Dispersivity αTh [m] | — | — | `alpha_Th` | `alpha_Th` | — |
| K | K | Hydraulic Conductivity K [m/s] | `hydraulic_conductivity` | — | — | — | `hk` |
| C_D | C_D | Electron Donor CD [mg/L] | `electron_donor` | `C_ED0` | `C_ED0` | `C_D` | `Cd` |
| C_A | C_A | Electron Acceptor CA [mg/L] | `electron_acceptor_o2` | `C_EA0` | `C_EA0` | `C_A` | `Ca` |
| γ | γ | Stoichiometric Ratio γ [-] | — | `gamma` | `gamma` | `gamma` | `gamma` |
