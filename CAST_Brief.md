# CAST — what a user can do with it

Briefing notes for the manuscript author, written from the user's side of the screen. Current code: branch `final`, Aug 2026.

## 1. The pitch

You have a contaminated site and a handful of measurements. CAST takes you from that to a defensible first estimate of how far the plume will travel — in a browser, without installing anything, without writing code, and without an account. You can screen the site through eight closed-form models in under a minute, run a full MODFLOW 6 transport simulation on the same parameters, compare all of it against 112 real field sites, and walk away with a PDF report.

## 2. Getting started takes no setup

Open the site and you are already working. The bundled **reference database of 112 contaminated sites** is the default data source, every model is open to visitors, and nothing asks you to register. An account exists only so you can save your own sites — everything else works as a guest, including the numerical and AEM simulations.

## 3. The workflow

**1 · Bring your site data.** Type one site into the form, or upload a CSV of many. The importer accepts the column names people actually use, tolerates blanks and `N/A`, and tells you what it did. Your sites are private to your account. Filter, sort, page through them, and export the table as CSV, XLSX or PDF at any point.

**2 · Look at the data first.** Bar chart of your plume lengths against the reference database, histogram, box plot — so you can see immediately whether your site is ordinary or an outlier before modelling anything.

**3 · Screen with the analytical and empirical models.** Pick a model, pick a site from the drop-down, and its stored parameters fill the form automatically. Fields that came from the database are labelled as such, so you always know which numbers are yours and which are defaults. Six analytical models — Liedl 2005 (2-D vertical), Liedl 2011 (3-D), Chu 2005, Ham 2004, Cirpka 2005, BIOSCREEN-AT — and two empirical ones, Maier & Grathwohl and Birla et al. with recharge. You get a plume length and a plot placing it against the field data.

**4 · Explore the sensitivity.** Every single-run page has **live sliders**. Drag a dispersivity and watch the plume length and the plot move. This is the fastest way to see which parameter your answer actually depends on, and it is the feature that reads best in a demonstration.

**5 · Compare across your sites.** Switch to multi-site mode, tick several sites, and the model runs once per site on that site's own parameters. The plot puts modelled plume length next to measured plume length for all of them at once — a direct read on whether the model works for your kind of site.

**6 · Go deeper with a simulation.** The numerical toolbox runs **MODFLOW 6** flow and transport for the same site, in either a **vertical cross-section** or a **horizontal plan view**. You see the simulated plume as an interactive contour plot. Runs happen in the background: you can leave the page, come back, and the result is waiting — or cancel it. Afterwards, and without re-running the solver, you can pull out a **concentration profile** along any line or a **gradient-vector field** showing where the plume is being consumed.

**7 · Or design your own source geometry.** The AEM toolbox lets you **draw the contaminant source as a shape on a canvas**. It is packed automatically with circular elements, solved analytically, and returns the steady-state plume for that geometry — not just the rectangular source every other model assumes. This is the most visually striking part of the tool.

**8 · Work backwards from a measurement.** The AEM inverse mode does the reverse of everything above: give it a plume length you actually measured, and it recovers the transport parameter that produces it — transverse or longitudinal dispersivity, source radius, source concentration, acceptor concentration or the stoichiometric ratio. For a practitioner with monitoring data and no dispersivity estimate, this is the most directly useful thing in the toolkit.[link to be connected]

**9 · Analyse whatever came out.** The data workbench takes your site table, any CSV, or the field from your last AEM run, and gives you histograms and kernel density estimates, scatter plots with fitted curves and confidence bands, contour and profile and quiver plots on gridded data, and a descriptive-statistics table. It also reads **MODFLOW binary output directly**, so a simulated head field can be contoured with the same tools as a measured concentration field. Axis labels are typeset properly from your column names, and every number carries two significant decimals whether it is a plume length in hundreds of metres or a trace concentration at 10⁻⁶.

**10 · Take a report away.** Every model exports the same branded PDF — inputs table, results, plots, plume images, institutional logos, timestamp, disclaimer. Raw MODFLOW binaries and the AEM concentration grid (CSV or NPZ) download separately if you want the numbers.

## 4. Things the tool does quietly for the user

Worth a sentence each — they are what makes it usable rather than merely functional.

- **A site is only offered to models that can actually use it.** Each model's own maths decides which sites appear in its drop-down: a model that divides by acceptor concentration will not offer you a site where that value is zero. Nothing is deleted — the site stays available to every model it does suit. [double check]
- **A missing value is not a dead end.** Parameters your site record does not carry fall back to sensible defaults rather than blocking the run.
- **Units are handled at the boundary.** Conductivity stored in m s⁻¹ is converted for the numerical model, with plausibility bounds so an implausible value is caught rather than silently simulated.
- **The same symbol means the same thing everywhere.** Form labels, dashboard tables and PDF reports all draw from one parameter registry, so notation never drifts between the screen and the report.
- **Long simulations do not block you.** They queue, run in the background, and can be cancelled; a multi-site comparison is capped so one click cannot hang the server.


