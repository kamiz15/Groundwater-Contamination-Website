# AEM Source Designer — "Simulation failed, check input" on vertical orientation

**Date:** 2026-06-24
**Component:** AEM forward simulation (`/aem` designer → `/aem/api/forward`)
**Status:** Diagnosed, awaiting code-owner confirmation before applying a fix.

---

## TL;DR

After the editable **"Parameters"** panel was removed from the web AEM designer
(`templates/aem_designer.html`) to match the reference tool `source_designer.py`,
the orientation became a fixed value. It was fixed to **`vertical`**, because that
is `source_designer.py`'s default (`ORIENTATION = "vertical"`).

For the geometries being drawn, a **vertical** run produces a result field that is
**entirely negative** (all electron-acceptor, no donor region inside the plotted
domain). The plotting code then builds `np.linspace(0, max_val, 11)` with
`max_val < 0`, which is a *decreasing* sequence, and matplotlib raises:

> `Contour levels must be increasing`

The job is reported to the UI as *"Simulation failed. Please check your inputs."*

**The simulation/solver is fine.** It runs to completion; only the final plot crashes.
This is **not** caused by the parameters-window change other than that the change
fixed the orientation to the source default. The same crash exists in the reference
code (see "Is the source affected?" below).

---

## What the user observed

- Previously, runs worked ("the true one").
- After the parameters window was removed, every run reports **"simulation failed, check input."**
- The user reports using it "the same way as the true one."

## What actually differs

The earlier **successful** jobs were **horizontal**; the **failing** jobs are **vertical**.
Evidence from the job database (`.numerical_jobs/jobs.sqlite3`, table `numerical_jobs`):

| job kind     | orientation | status   |
|--------------|-------------|----------|
| aem_forward  | horizontal  | **done** |
| aem_forward  | horizontal  | **done** |
| aem_forward  | vertical    | **failed** |
| aem_forward  | vertical    | **failed** |

The failing rows carry the error:

```
Contour levels must be increasing
  File "aem_jobs.py", line 367, in run_aem_forward -> sim.run()
  File "aem/at_simulation.py", line 407, in run -> self.plot_result()
  ... contourf(levels=donor_levels) ...
```

## Root cause (reproduced)

The failing config was replayed through the solver with plotting bypassed to inspect
the field the plot code receives:

```
RESULT  min = -7.96538   max = -7.78583    any_neg = True   any_pos = False
```

The whole field is negative. In `aem/at_simulation.py` `plot_result()`:

```python
max_val = float(np.max(self.result))   # = -7.7858  (<= 0)
...
donor_levels = np.linspace(0, max_val, 11)        # linspace(0, -7.79, 11) -> DECREASING
acceptor_levels = np.linspace(-abs_min, 0, 9)
...
donor = ax.contourf(X, Y, self.result, levels=donor_levels, ...)   # <-- raises here
```

Because the donor sources (c = +10) sit at the top edge of a vertical domain
(`dom_ymax = 0`, sources shifted to y ∈ ~[-0.4, 0]) while the domain extends down to
`dom_ymin ≈ -5.47` and out to `dom_xmax ≈ 150`, the small positive donor sliver is
not captured on the coarse grid (`dom_inc = 0.95`). The net concentration sampled on
the grid is negative everywhere, so `max(self.result) < 0` and the donor level array
is invalid.

(The symmetric failure mode exists for a field with no acceptor: `abs_min == 0` makes
`np.linspace(-abs_min, 0, 9)` = `linspace(0, 0, 9)`, also non-increasing.)

## Is the source ("true one") affected?

**Yes — identically.** `Downloads/src/src/at_simulation.py` and
`cast_landing_demo/aem/at_simulation.py` are byte-for-byte identical in `plot_result`
(only the package import lines differ: `from .at_config` vs `from at_config`). The
domain-generation logic also matches: `source_designer.py:build_config` and the web's
`static/aem.js:referenceConfig` apply the same vertical shift and the same
`dom_*` formulas.

Therefore, running this same vertical geometry through the reference simulation would
hit the same `Contour levels must be increasing` crash. The reference workflow simply
never exercised this path — `source_designer.py` only *designs* geometry; it does not
run `ATSimulation`, and prior real runs were horizontal. The web app's own default
sample is also horizontal (`aem_jobs.py: DEFAULT_SAMPLE = "source_config_horizontal.json"`).

## Decision (2026-06-24): default orientation set to `horizontal`

After confirming that tiny-source **vertical** designs are non-physical on the fixed
grid (all-acceptor, no donor — in the web *and* the reference), the fixed orientation
was changed from `vertical` to **`horizontal`** in `templates/aem_designer.html`.
Rationale: horizontal is the source's actual working run config
(`simulation_config.json`) and the only orientation that resolves a plume for the
designer's tiny sources. Verified: the same drawn geometry, rebuilt as horizontal,
yields `result_max = 3.306 > 0`, completes, and returns a plume (`L_max = 19`) instead
of crashing. (`validation_passed` may still be `False` for a weak plume — advisory
only, as in the reference, which still plots it.)

> ⚠️ The app code is baked into the Docker image (`Dockerfile: COPY . /app`); only
> `./static`, `./nginx`, and the `numerical_jobs` volume are mounted. **Any code or
> template change requires `docker compose up -d --build`** to take effect.

## Current state of the code

- `templates/aem_designer.html` — parameters window removed; orientation is a hidden
  input fixed to **`horizontal`** (see decision above).
- `aem/at_simulation.py` — **left byte-identical to the reference**
  (`Downloads/src/src/at_simulation.py`); only the two package-relative import lines
  differ. No simulation logic, including `plot_result()`, was modified.

- `aem_jobs.py: run_aem_forward()` — **APPLIED FIX (2026-06-24), web-layer only.**
  The reference's `validate_solution()` already classifies a non-physical field
  (`result_max <= ca` = "no donor above background", or `result_min >= -ca/2`) just
  before the unconditional `plot_result()`. The web layer now honours that
  classification: it wraps `sim.run()` and, when the reference's plotting step raises
  on such a field, surfaces the reason the reference already computed instead of the
  opaque matplotlib error:

  ```python
  try:
      sim.run()
  except Exception as exc:
      if getattr(sim, "validation_passed", None) is False:
          raise ValueError(
              "Simulation did not produce a physically meaningful plume "
              f"({getattr(sim, 'validation_reason', '') or 'failed validation'}). "
              "The source geometry is likely too small or sparse to resolve on the "
              "current grid increment — try larger/denser sources, a finer grid, or "
              "horizontal orientation."
          ) from exc
      raise
  ```

  This keeps the shared simulation code faithful to the source and reuses the
  already-plumbed `validation_passed`/`validation_reason`. The web serves the forward
  result as arrays (`aem_routes.py:aem_job_result`), so the source's diagnostic
  `plot_result()` PDF is unused either way.

  Verified:
  - failing vertical config → `ValueError: ... result_max=-7.786 <= ca=7.900: no
    donor above background ...` (clean failure, no matplotlib crash leaks).
  - valid horizontal sample → completes, returns `AEMForwardResult`,
    `validation_passed=True`, `L_max=265`. Behaviour unchanged for physical configs.

**Note for the owner:** this makes the failure *graceful and explained*; it does not
make tiny-source vertical geometries *succeed* (they are non-physical on this grid by
the source's own definition). The user-facing job message
(`aem_routes.py:aem_job_status`) is still the generic "Simulation failed. Please check
your inputs and try again." — the specific reason is now in the job `error` field/logs.
Surfacing that reason in the UI, and/or the orientation/grid-resolution decisions below,
are still open for you to confirm.

## Options for the owner to choose

1. **Fix the orientation to `horizontal`** (one-line change in `aem_designer.html`):
   matches the only orientation that has ever run successfully and the web's default
   sample. Does **not** touch the source-shared simulation code. Trade-off: differs
   from `source_designer.py`'s `vertical` default.

2. **Guard the contour levels in `plot_result()`** so a single-sign field renders the
   empty side as blank instead of crashing (2-line change). Lets the source's `vertical`
   default work. Trade-off: a small divergence from the reference `at_simulation.py`
   (though arguably a latent bug the reference shares):

   ```python
   donor_levels = np.linspace(0, max_val if max_val > 0 else 1.0, 11)
   acceptor_levels = np.linspace(-(abs_min if abs_min > 0 else 1.0), 0, 9)
   ```

3. **Leave as-is** (strictly source-faithful) and accept that vertical geometries of
   this type fail. Document it as a known reference-code limitation.

## Why has this never shown up in the source code?

Three reasons, in order of importance:

1. **The source's real run config is horizontal with large sources.**
   `Downloads/src/src/simulation_config.json` — the hand-authored config the source
   pipeline actually runs — is `orientation: "horizontal"` with two **r = 1.0 m**
   donor circles (c = 5) in a ±20 m domain. That produces a well-resolved plume with
   both a donor (positive) region and an acceptor (negative) region, so
   `max(result) > 0` and the contour levels are valid.

2. **The tiny-source vertical designer exports were never run end-to-end.**
   `source_designer.py` only *draws and exports* geometry; nothing in the source
   pipeline runs those exports through `ATSimulation.plot_result()`. Proof: the
   source's own bundled sample `designer_exports/source_config_c2e26e25.json`
   (23 circles, r ≤ 0.0375 m, vertical), run through the identical solver, yields:

   ```
   RESULT  min = -8.5133   max = -7.7686   any_pos = False
   ```

   i.e. it would crash with `Contour levels must be increasing` exactly like the
   user's config. The latent bug is in the source too; it was simply never exercised.

3. **Physical/discretisation cause.** The designer's donor sources are tiny
   (r ≈ 0.003–0.05 m) and sit at the top edge of the vertical domain
   (`dom_ymax = 0`). On a `dom_inc ≈ 1 m` grid, no grid node lands inside the small
   positive donor sliver, so every sampled node is acceptor-dominated (negative).
   With large sources (source's real config, r = 1 m) or a fine grid the donor
   region is resolved and the field spans both signs.

## Can it be avoided by restricting input? Does the source do anything similar?

**Input validation:**

- **Source (`at_config.py`)** performs *no* input validation or clamping — it reads
  values with `.get()` defaults and only raises on an unknown element `kind` or a
  missing ellipse semi-axis. There is no source precedent for restricting input.
- **Web (`aem_routes.py:_validated_config`)** adds bound checks (positive numbers,
  coordinate/element/`num_cp`/`num_terms` ranges, and a `MAX_GRID_CELLS` *upper*
  cap). None of these prevent this case: orientation `vertical` is allowed, and the
  cap is a maximum cell count, not a *minimum resolution*. Nothing requires the grid
  to actually resolve the sources.

**The source DOES already detect this exact condition — but on the output, not the input.**
`at_simulation.py:validate_solution()` (called at line 388, *before* `plot_result()`
at 407) PASSES only if:

```
(a) result_max >  ca          # donor concentration exists above background
(b) result_min < -ca * 0.5    # acceptor depletion present
```

For the failing vertical field, `result_max = -7.78` is **not** `> ca (7.9)`, so
`validate_solution()` records **FAIL — "no donor above background."** But it only
sets `self.validation_passed`/`self.validation_reason` and prints; it does **not**
raise or skip plotting, so the run proceeds into `plot_result()` and crashes. The
web already carries this flag through to the result object
(`aem_jobs.py: AEMForwardResult.validation_passed / validation_reason`).

**Implications for a fix (for discussion — not yet applied):**

- A true *input* restriction can't directly know the field will be single-sign
  (it depends on the solve + grid). The closest input-level guard is a **minimum grid
  resolution relative to source size** (e.g. require `dom_inc` small enough, or enough
  cells across the source zone) so the donor region is resolved. Neither codebase does
  this today, and it would increase runtime.
- The **source-faithful** avenue is to honour the source's *own* validation: when
  `validation_passed` is False (specifically `result_max <= ca`), treat the run as a
  failed/non-physical result and avoid the degenerate plot, instead of letting
  `contourf` raise. This reuses logic the source already computes, rather than adding
  a new contour-level guard.

## Question for the code owner

Which orientation is intended as the *fixed* default for the AEM web designer now that
the parameters window is gone — `vertical` (source designer default) or `horizontal`
(the only orientation that currently renders)? And should the `plot_result()` contour-level
degeneracy be fixed in the simulation code, or is it acceptable to leave it matching the
reference exactly?
