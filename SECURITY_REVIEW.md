# Authentication & Security Review — CAST

Date: 2026-06-11
Scope: user authentication, session management, authorization, and the Flask ↔ Panel ↔ nginx trust boundary that protects user site data.

## Summary

The existing code already had several good practices in place: parameterized SQL everywhere (no injection found), password hashing with Werkzeug, CSRF protection on mutating routes, rate limiting, and generic database error messages. The review found one **critical** authorization flaw and a set of **high/medium** hardening gaps. All are fixed below; the change is verified by the existing test suite plus eight new regression tests.

## Findings and fixes

### 1. Critical — Broken access control (IDOR) in the Panel apps
Every Panel model app derived the user identity from the client-controllable `?email=` query parameter (`email = query_str("email", "")`) and used it to load that user's site data (`get_user_sites(email)`). The nginx `auth_request` gate only confirmed that *some* valid session existed — it never checked that the email belonged to the logged-in user. Any authenticated user could edit the iframe URL to `?email=victim@example.com` and read another user's confidential site data.

Fix: identity now comes from a non-spoofable, reverse-proxy-injected header instead of the URL.
- `app.py` `/auth/check` now returns the authenticated user's email in an `X-User-Email` response header.
- `nginx/default.conf` captures it from the auth subrequest (`auth_request_set $auth_email $upstream_http_x_user_email`) and forwards it to Panel as `X-Auth-Email` via `proxy_set_header`, which overwrites any value the browser tried to send.
- New `panel_auth.py` `authenticated_email()` reads only that trusted header. The 14 Panel apps now call it instead of `query_str("email", ...)`. A query-string fallback exists solely for running Panel standalone in local dev and is gated behind `PANEL_TRUST_QUERY_EMAIL` (default **off**).

### 2. High — Debug mode defaulted on
`FLASK_DEBUG` defaulted to `True`, exposing the interactive Werkzeug debugger (remote code execution) and stack traces if an env var was missing. Default flipped to `False` in `settings.py`; dev still opts in via `.env`.

### 3. High — Session cookies not hardened
No `Secure`, `SameSite`, or explicit `HttpOnly` flags were set on the login/remember cookies. Added in `app.py`: `HttpOnly` + `SameSite=Lax` on both cookies, and `Secure` driven by the new `SESSION_COOKIE_SECURE` setting (default on; off for plain-HTTP dev).

### 4. High — Rate-limit bypass via spoofable header
The login/registration rate limiter keyed on the leftmost `X-Forwarded-For` entry, which is fully client-controlled — an attacker could rotate it to evade the limit and brute-force credentials. `security._client_address()` now uses `X-Real-IP` (set by the trusted proxy, which overwrites client input) and is gated by `TRUST_PROXY_HEADERS`; the spoofable XFF path is removed.

### 5. Medium — No registration input validation
Registration accepted any password (including a single character) and any string as an email. Added in `security.py` / `app.py`: email format check, username length cap (matches the DB column), and a password length policy (min 8, max 256). The policy intentionally follows NIST SP 800-63B — length over composition rules — so strong passphrases are accepted and the max length caps password-hashing cost (a cheap DoS vector).

### 6. Medium — User enumeration via login timing
Login skipped the password hash entirely when the email didn't exist, so non-existent accounts responded measurably faster. `authenticate()` now runs a comparison against a precomputed dummy hash on the no-user path, equalizing response timing.

### 7. Low — Secrets hygiene
`.env.example` now documents how to generate a strong `SECRET_KEY` and explains every new flag. The committed dev `.env` still uses placeholder secrets (it is git-ignored) — see remaining recommendations.

## Files changed
- `app.py` — cookie hardening, registration validation, constant-time login, `X-User-Email` on `/auth/check`.
- `security.py` — email/password validators, rate-limit IP source fix.
- `settings.py` — `FLASK_DEBUG` default off; new `SESSION_COOKIE_SECURE`, `TRUST_PROXY_HEADERS`, `PANEL_TRUST_QUERY_EMAIL`.
- `panel_auth.py` (new) — trusted `authenticated_email()`.
- 14 Panel apps (`panel_*`, `bioscreen_panel.py`) — use `authenticated_email()` instead of the query param.
- `nginx/default.conf` — inject trusted `X-Auth-Email` into the Panel upstream.
- `.env`, `.env.docker`, `.env.example` — new flags with secure-by-default production values.
- `tests/test_auth_hardening.py` (new) — 8 regression tests.

## Verification
- `tests/test_auth*.py` and the route/proxy/schema suites: **passing** (85 passed, 4 skipped in the auth-related selection; 8 new hardening tests pass).
- The only failing tests (`test_numerical_models.py`, 4) require the MODFLOW6 binary, which is absent in the review sandbox — pre-existing and unrelated to this change.

## Remaining recommendations (not auto-applied)
These need infrastructure or product decisions rather than a code edit:

1. **Terminate TLS.** nginx currently serves plain HTTP on port 80, so `SESSION_COOKIE_SECURE` is forced off in the shipped configs. Put HTTPS in front and set `SESSION_COOKIE_SECURE=true` before any real-user deployment. This is the single most important deployment step.
2. **Rotate production secrets.** Generate a unique `SECRET_KEY` and a real `DB_PASSWORD` per environment; never ship `root`/`dev-secret-key-change-me`.
3. **Breached-password check** (e.g. the HaveIBeenPwned k-anonymity range API) at registration, per NIST 800-63B.
4. **Account lockout / progressive backoff** keyed on the account, complementing the per-IP rate limit, to slow targeted brute force.
5. **Email verification and password reset** flows — currently absent; verification also prevents registering arbitrary addresses.
6. **Consider MFA** for an application holding confidential site data.

---

# Database Review (round 2) — users & sites tables

Date: 2026-06-11
Scope: the MySQL `users` and `sites` tables, every SQL call site, the data going into them (account registration + site model inputs, manual and CSV), and the numerical-jobs store.

## What was already sound
All SQL uses parameterized queries — no injection was found, including the CSV import path. Site reads/writes are correctly scoped to the logged-in user's email, so there is no cross-user data leak on the `sites` table. The Docker compose runs MySQL as a non-root application user.

## Findings and fixes

### D1. High — User-supplied site values were not validated before storage
Numeric site inputs (thickness, plume length/width, conductivity, donor/acceptor concentrations) were coerced with a permissive `float()` and stored as-is. Negative values, `NaN`, and `Infinity` could reach the database, producing physically meaningless data that breaks the model math (and `NaN`/`Inf` raise opaque MySQL errors surfaced as a generic 503). Text fields (`site_unit`, `compound`) had no length check against their column widths, risking silent truncation or errors.

Fix (`data_queries.py`): a single `_clean_site_payload()` choke point now validates every row from both the manual and CSV paths — finite, non-negative numerics, and text capped to the column width — raising a clear `ValueError` that the site page already surfaces to the user.

### D2. Medium — Unbounded CSV upload
`insert_sites_bulk` inserted every parsed row with no ceiling, so one upload could write an unbounded number of rows (storage/CPU DoS). Added `MAX_SITE_UPLOAD_ROWS` (default 10,000); oversized uploads are rejected with a clear message. The whole upload is validated before any insert, so a single bad row aborts the batch (no partial writes).

### D3. Medium — No request body size limit
Flask had no `MAX_CONTENT_LENGTH`, so a large body (CSV or the base64 report-export payload) could exhaust memory when not behind nginx. Added `MAX_REQUEST_BYTES` (default 50 MB, matching `client_max_body_size`) and wired it into the app config.

### D4. Medium — Schema permitted invalid/orphan rows
`users.username`, `users.email`, `users.password_hash`, and `sites.user_email` were all nullable. A NULL `password_hash` is an auth hazard and a NULL `user_email` orphans site data from its owner. Added `NOT NULL` constraints (and kept `email UNIQUE`) in both the runtime schema (`data_queries.py`) and the bootstrap `db_setup.sql`. Note: `CREATE TABLE IF NOT EXISTS` only applies these to fresh databases — an existing database needs a one-time `ALTER TABLE` migration (see below).

### D5. Low — Numerical jobs are not owner-scoped (accepted risk, documented)
The `numerical_jobs` SQLite store keeps each job's model parameters but has no owner column; `GET /numerical/jobs/<id>` and the cancel endpoint authorize "any logged-in user," not "the owner." Exposure is bounded because job IDs are `uuid4` (128-bit, unguessable) and IDs are only returned to the submitting client. Fixing it properly means adding an `owner_email` column plus a migration and threading identity through the worker and six call sites (including the Panel apps). Given the strong mitigation already in place, this is listed as a recommended follow-up rather than changed in this pass, to avoid a risky change for marginal benefit.

## Files changed (round 2)
- `data_queries.py` — `NOT NULL` schema, `_clean_site_payload()` validation, bulk row cap.
- `settings.py` — `MAX_SITE_UPLOAD_ROWS`, `MAX_REQUEST_BYTES`.
- `app.py` — `MAX_CONTENT_LENGTH` wired into config.
- `db_setup.sql` — `NOT NULL` constraints to match runtime schema.
- `tests/test_site_validation.py` (new) — 10 regression tests.

## Verification (round 2)
Full suite: **187 passed, 4 skipped**; the only 4 failures are the pre-existing MODFLOW6-binary tests, unrelated to these changes. The schema-consistency test (runtime schema vs. `db_setup.sql`) passes.

## Migration note for existing databases
New deployments get the constraints automatically. For an already-populated database, clean any offending rows and then apply, roughly:

```sql
-- Ensure no NULLs remain first, then:
ALTER TABLE users
    MODIFY username VARCHAR(100) NOT NULL,
    MODIFY email VARCHAR(150) NOT NULL,
    MODIFY password_hash VARCHAR(255) NOT NULL;
ALTER TABLE sites
    MODIFY user_email VARCHAR(150) NOT NULL;
```

## Additional follow-ups
- Owner-scope the numerical-jobs store (D5).
- Add a `created_at` timestamp to `users`/`sites` for auditing.
- Normalize email casing at registration to remove any ambiguity (MySQL's default case-insensitive collation currently masks this).

---

# Performance Review (round 3)

Date: 2026-06-11
Scope: Flask endpoint latency, database connection behaviour, page weight, and per-request waste. Profiled with a stubbed in-memory DB (so connection *counts* are exact; real-world connect cost is additional).

## Findings and fixes

### P1. High — No database connection pooling
Every query opened a brand-new MySQL connection (TCP + auth handshake) and tore it down: `/sites` opened 3 per request, and every authenticated request opened at least 1 (Flask-Login's user loader). Under load this also risks exhausting MySQL's connection limit. Fix (`data_queries.py`): a process-wide `MySQLConnectionPool` (size via `DB_POOL_SIZE`, default 10). `connection.close()` now returns the connection to the pool, so no call sites changed.

### P2. Medium — `/sites` ran a duplicate query whose result was never used
The route fetched all of the user's sites twice (`get_user_sites` + `get_user_sites_rows`); the first result (`table_data`) was passed to the template but never referenced. Removed the dead query and the unused template vars. DB connections on `/sites`: 3 → 2 (the remaining 2 are the user loader + the single data query).

### P3. Medium — ~2 MB of render-blocking Bokeh JS on every page
`base.html` put 6 blocking `<script>` tags (BokehJS suite from CDN) in the `<head>` of *every* page, although only the three Analysis Visualisation pages embed Bokeh in the parent document (model pages load Panel in an iframe with its own resources). Moved the scripts into a `{% block bokeh_js %}` that only the plot templates override. Head scripts on `/`: 6 → 0; on `/plot_bar`: still 6.

### P4. Low — Reference-CSV miss re-scanned on every plot render
`plot_functions._load_reference_df()` cached a successful load but not a miss, so when `static/original.csv` is absent (it is not in the repo) every plot request re-checked 4 filesystem paths and logged a warning. The miss is now cached; the lookup happens once per process.

### P5. Low — Rate-limiter memory growth
The in-memory rate-limit map kept one entry per (endpoint, client IP) forever; expired buckets were emptied but never evicted, growing without bound across distinct IPs. Fully-expired buckets are now deleted during the pruning pass.

## Measured results (stub DB, p50 over 12 requests)
- `/` 0.8 ms, 0 head scripts (was 6); `/sites` 2 DB connections/request (was 3); plot pages unchanged at ~44 ms (Bokeh figure construction — inherent to the page) but no longer re-scan for the CSV.
- With real MySQL, P1 additionally removes a connect/auth round-trip (typically 2–10 ms) from every query on every request.

## Files changed (round 3)
`data_queries.py` (pool), `site_routes.py` (dead query removed), `templates/base.html` + 3 plot templates (Bokeh block), `plot_functions.py` (miss cache), `security.py` (bucket eviction), `tests/test_auth.py` (assertion updated to the single-query behaviour).

## Verification (round 3)
Full suite: 181 passed, 4 skipped (MODFLOW-binary tests excluded as before). Verified plot pages still carry BokehJS while all other pages carry none.
