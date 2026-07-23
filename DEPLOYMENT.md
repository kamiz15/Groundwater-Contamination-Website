# CAST Deployment Guide

Checklist for hosting the CAST stack on institutional servers (written for the
University of Tübingen and IIT Delhi deployments). Each site runs its own
independent copy of the Docker Compose stack: nginx → Flask/Gunicorn + Panel →
MySQL. Nothing is shared between sites.

## 1. Per-site configuration (required)

Create a `.env` next to `docker-compose.yml` on each server. Start from
`.env.example` and set:

| Variable | Tübingen / Delhi value |
|---|---|
| `SECRET_KEY` | Unique per site. Generate: `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Never reuse across sites — a leaked key at one site must not compromise the other. |
| `DB_USER`, `DB_PASSWORD`, `MYSQL_ROOT_PASSWORD` | Unique per site. |
| `PANEL_ALLOW_ORIGINS` | Must include the site's public hostname, e.g. `cast.uni-tuebingen.de` or `cast.iitd.ac.in`. If missing, every model page's Panel iframe shows a blank panel (websocket refused). Comma-separated; keep the localhost entries for on-host smoke tests. |
| `SESSION_COOKIE_SECURE` | `true` as soon as the site is served over HTTPS (see §2). The login cookie will not work over plain HTTP with this on. |
| `TRUST_PROXY_HEADERS` | `true` (the bundled nginx injects `X-Real-IP`). |
| `PANEL_TRUST_QUERY_EMAIL` | `false` in production, always. |

The non-secret defaults (`MF6_EXE`, `NUMERICAL_*`, ports) come from the
committed `.env.docker` and rarely need changing.

## 2. TLS

The bundled nginx listens on plain HTTP :80. Two supported setups:

1. **Institutional front proxy (recommended at both unis).** The campus
   reverse proxy terminates HTTPS and forwards to this stack over HTTP.
   - Set `SESSION_COOKIE_SECURE=true`.
   - Add HSTS at the front proxy, not here.
   - **Required:** configure real client IPs, or rate limiting will treat the
     whole campus as one user (everyone shares the 5/min login bucket).
     Uncomment the `set_real_ip_from` block in `nginx/default.conf` and set it
     to the front proxy's address/CIDR.
2. **Direct exposure.** Add a TLS server block (certbot or institutional
   certificate) to `nginx/default.conf` and redirect :80 → :443. Then set
   `SESSION_COOKIE_SECURE=true` and add HSTS here.

## 3. Start / update

```bash
docker compose up --build -d        # first start and every update
docker compose ps                   # all services should be "healthy"
```

Update procedure: `git pull`, then `docker compose up --build -d`. User data
(MySQL) and numerical job results survive rebuilds — they live on the named
volumes `mysql_data` and `numerical_jobs`. Solver scratch files are ephemeral
by design (`NUMERICAL_RUN_ROOT=/tmp/numerical_runs` inside the container).

## 4. Backups (per site)

The only state worth backing up is the MySQL volume and, optionally, finished
job reports:

```bash
# nightly dump (add to cron on the host)
docker compose exec -T db sh -c 'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" cast_project' \
  | gzip > /var/backups/cast/cast_$(date +%F).sql.gz
```

Test a restore once before go-live. Job results (`numerical_jobs` volume) are
reproducible by re-running simulations; back them up only if report retention
matters.

## 5. Operational notes

- **Rate limiting** is in-memory and per Gunicorn worker (4 workers), so the
  effective limit is up to 4× the nominal per-endpoint figure, and it resets
  on restart. Fine for these deployments; switch to a shared store (Redis)
  only if the sites ever scale beyond one Flask container.
- **Containers run as a non-root user** (`cast`, uid 10001). If you mount
  extra paths into the containers, they must be writable by that uid.
- **Solver limits**: `NUMERICAL_MAX_CELLS=40000` and
  `NUMERICAL_SOLVER_TIMEOUT_S=120` cap what one simulation can consume.
  `NUMERICAL_MAX_CONCURRENCY` (default 2) caps parallel MODFLOW runs — size it
  to the server's cores at each site.
- **Reproducible builds**: after the first image works at one site, snapshot
  exact dependency versions so the second site builds the same thing:
  `docker compose exec flask pip freeze > requirements.lock`, then install
  with `-c requirements.lock` in the Dockerfile (or copy the built image).
- **Logs**: all services log to stdout/stderr → `docker compose logs`.
  Gunicorn access logs are enabled. No log files are written inside the
  containers.
- **Health checks**: nginx, flask, panel, and db all define Docker
  healthchecks; `restart: unless-stopped` brings them back after reboots.

## 6. Pre-go-live smoke test (each site)

1. `docker compose ps` → four healthy services.
2. Register an account, log in, log out (over HTTPS, cookie must persist).
3. Upload the sample CSV, confirm rows appear and one can be deleted.
4. Open a Liedl single page → Panel iframe renders (checks
   `PANEL_ALLOW_ORIGINS`).
5. Run a numerical vertical export → job queues, report PDF downloads.
6. `docker compose restart flask` → previously finished report still
   downloadable (checks the `numerical_jobs` volume).
7. From two different machines, fail one login each → no shared 429 (checks
   real-IP configuration).
8. `curl -i http://<host>/health` → `204` (also confirms DB connectivity).

## 7. Rollback

Every deploy is a git commit plus a rebuilt image, so rolling back is
redeploying the last good commit. Tag each deploy so "last good" is findable:

```bash
git tag deploy-$(date +%F)   # after each successful update
# rollback:
git checkout <last-good-tag>
docker compose up --build -d
```

Schema changes are additive and idempotent (`ensure_schema` only ADDs
columns), so older code runs safely against a newer database — a code
rollback normally needs no DB restore. If data was corrupted, restore the
latest §4 dump:

```bash
gunzip -c cast_YYYY-MM-DD.sql.gz \
  | docker compose exec -T db sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" cast_project'
```

## 8. Secret rotation

Per site: rotate once per semester, and immediately whenever someone with
server access leaves the project.

- `SECRET_KEY`: generate a new one (§1), update `.env`, restart flask+panel.
  Every user is logged out once — harmless.
- `DB_PASSWORD` / `MYSQL_ROOT_PASSWORD`: `ALTER USER ... IDENTIFIED BY ...`
  in MySQL, update `.env`, restart the stack.

## 9. Data protection runbook

- **Erasure request**: `DELETE FROM users WHERE email = '<user>';` — the
  `ON DELETE CASCADE` foreign key removes all their site rows with it.
- **Breach**: Tübingen → university DPO within 72 h (GDPR; authority: LfDI
  Baden-Württemberg). Delhi → Data Protection Board of India AND affected
  users (DPDP: every breach, no severity threshold).
- **Logs** contain IP addresses (personal data). docker-compose caps them at
  10 MB × 5 files per service; do not raise without a retention reason.
- **Before go-live**: complete every `[FILL IN]` placeholder in
  `templates/privacy.html` and `templates/imprint.html` (controller
  addresses, DPO/grievance-officer contacts).
