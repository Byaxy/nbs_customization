# AGENTS.md

## Bench vs App

- Bench root is `/home/byaxy/frappe/nbs_customization` (contains `apps/`, `sites/`, `config/`, `Procfile`). All `bench` commands run from here, not from `apps/nbs_customization/`.
- Git repo is `apps/nbs_customization/` (only it has `.git`). Edit app code there; run bench ops from bench root.
- `bench` binary is `~/.local/bin/bench` (not `env/bin/bench`). Use bare `bench --site nbs.localhost <cmd>` — never bare `bench migrate`.

## App Layout (nested namespace — read before creating files)

- `apps/nbs_customization/nbs_customization/` — app package: `hooks.py`, `modules.txt`, `patches/`, `public/`, `fixtures/`, `templates/`
- `apps/nbs_customization/nbs_customization/nbs_customization/` — module `NBS Customization` (`.frappe` marker): `doctype/`, `report/`, `page/`, `print_format/`, `workspace_sidebar/`
- Verify: `bench --site nbs.localhost console` → `frappe.get_module_path("NBS Customization")`
- All doctypes go under `.../nbs_customization/doctype/<doctype_name>/` (inner module); never `.../nbs_customization/nbs_customization/doctype/` (outer package — Frappe won't load). API/controllers go at package level (`nbs_customization/controllers/`, `nbs_customization/api.py`).

## Installed Skills (`.agents/skills/` — copied from `ccu`/`samdell-sms`, source `frappe/skills`)

- **frappe-app-dev** — Frappe/ERPNext backend: DocTypes, controllers, whitelisted APIs, `frappe.db`/`qb`, hooks, permissions, enqueue, realtime, caching, testing, bench CLI. Load only needed `references/*.md` (see `SKILL.md:40-57`).
- **code-style** — Keep functions small, files <300 lines, public functions top / utilities bottom, terse why-comments.
- **ui-design** — Desk/page polish: restraint, spacing/gap+flex, lane alignment, tweak panel for new features.

Locked in `skills-lock.json` (hashes `0580e1d...`, `37aa49...`, `c3dec2...`).

## Browser Automation (agent-browser — global)

- Global install at `~/.claude/skills/agent-browser/` + `~/.agent-browser/`; `agent-browser --help` and `agent-browser skills get core --full` for workflows.
```
agent-browser open http://nbs.localhost:8003
agent-browser snapshot -i                    # refs @e1, @e2
agent-browser click @e1 / fill @e2 "text"
agent-browser screenshot /tmp/opencode/shots/<name>.png
agent-browser close
```
- Re-snapshot after any navigation — refs go stale. Chrome from `~/.cache/puppeteer/chrome/`; `--no-sandbox` in `~/.agent-browser/config.json`.
- UI workflow: save every screenshot to `/tmp/opencode/shots/` + paired `snapshot` text; `record start <file> ... record stop` for video.
- Local login: `http://nbs.localhost:8003` / `Administrator` / `admin`

## Environment

- Site: `nbs.localhost` (`sites/nbs.localhost/site_config.json`). DB: mariadb `_604573664721aaa5`. Ports — web `8003`, redis_cache/redis_socketio `13003`, redis_queue `11003`, socketio `9003`, file_watcher `6790` (`sites/common_site_config.json:2-17`).
- Python `>=3.14` via `uv` (`apps/nbs_customization/pyproject.toml:7`). Build backend `flit_core`. Venv at `env/` (seeded via uv, `env/pyvenv.cfg`). Install app deps via `bench pip` or `uv pip` inside bench, not plain `pip`.
- Apps installed (`sites/apps.txt:1-4`): `frappe`, `hrms`, `erpnext`, `nbs_customization` — load order matters for hooks/fixtures.

## Commands

```bash
# run from bench root (/home/byaxy/frappe/nbs_customization)
bench start                          # Procfile: redis_cache, redis_queue, web :8003, socketio, watch, schedule, worker
bench --site nbs.localhost migrate   # runs patches.txt pre/post sync + setup.py:after_migrate
bench --site nbs.localhost clear-cache
bench --site nbs.localhost console
bench --site nbs.localhost mariadb
bench build --app nbs_customization  # or bench build --apps frappe,erpnext,nbs_customization
bench watch                          # live JS/CSS rebuild
```

## Testing

- Framework: `frappe.tests.IntegrationTestCase` (`apps/nbs_customization/nbs_customization/tests/test_*.py`). Requires live MariaDB + Redis + site `nbs.localhost`.
```bash
bench --site nbs.localhost run-tests --app nbs_customization
bench --site nbs.localhost run-tests --app nbs_customization --module nbs_customization.tests.test_check_clearing
bench --site nbs.localhost run-tests --app nbs_customization --module nbs_customization.tests.test_check_clearing --test TestCheckClearing.test_receive_check_forced_to_clearing_and_cleared_to_bank
bench --site nbs.localhost run-tests --app nbs_customization --test test_daily_income_and_expense
```
- Check clearing tests call `_ensure_check_clearing_setup()` inside the test transaction — don't assume `Check` Mode of Payment exists outside tests.

## Lint / Format

- Config in `apps/nbs_customization/pyproject.toml:22-61` and `.pre-commit-config.yaml:1-69`: `ruff` (line-length `110`, `target-version py314`, format `quote-style double` + `indent-style tab`), `eslint` + `prettier` for JS/Vue/SCSS.
- `.editorconfig:13-14` enforces `indent_style = tab`, `indent_size = 4` for `*.py,*.js,*.vue`; JSON doctypes use `space` indent `1`.
- Run from `apps/nbs_customization/`:
```bash
pre-commit install          # once (README.md:20-21)
pre-commit run --all-files  # ruff (isort + lint + format), prettier, eslint, trailing-whitespace, check-ast/json/toml/yaml
# or targeted:
ruff check --fix nbs_customization && ruff format nbs_customization
```

## Architecture

- Entrypoints: `apps/nbs_customization/nbs_customization/hooks.py:1-410` — overrides `frappe.desk.query_report.run/export_query` to `report_customizer.run` (`report_customizer.py:52-132`), injects desk assets (`app_include_css/js:28-38`, `doctype_js/list_js:336-349`), and wires `doc_events` for Sales/Purchase/Stock/Delivery Note/Payment Entry/Print Format (`hooks.py:351-410`) to `nbs_customization/controllers/` and `nbs_customization/nbs_customization/doctype/`.
- Reports: `nbs_customization/nbs_customization/report/{cheques_in_transit,daily_income_and_expense}/`; dashboard page `nbs_customization/nbs_customization/page/daily_income_expense` (both share logic — keep in sync, tested together in `test_daily_income_and_expense.py:278-350`).
- After-migrate side effects (`nbs_customization/setup.py:after_migrate:388-442`): drops legacy `paying_account` column (raw `information_schema` check, not `has_column` — Redis cache is stale), injects Selling/Accounting/Invoicing Workspace Sidebar items after `Sales Invoice` / `Repost Payment Ledger`, creates `Cheques in Transit - Inward/Outward` accounts under Receivable/Payable groups + `Check` Mode of Payment (with `is_check` + clearing accounts).
- PDF pipeline: `pdf_patch.apply_patches` on `before_request` (`hooks.py:221`) + monkey patch in `nbs_customization/__init__.py:9-28` (fixes `print_designer` `Browser.prepare_options_for_pdf` footer `paperHeight`). Both touch `print_designer.pdf` — test PDF changes manually via Print Preview.
- Fixtures (`hooks.py:274-333`): `Custom Field` (28 fields) + `Carrier` auto-exported via `bench --site nbs.localhost export-fixtures`.

## Gotchas

- `report_customizer.py:95-132` captures original `run/export_query` at import time and monkey-patches `_qr_module.run` only during `export_query` — don't move the import inside functions or exports lose customizations.
- Cheque clearing accounts have no `account_type` (stay out of Bank/Cash pickers); validation forces `destination_account` to Bank/Cash only (`tests/test_check_clearing.py:162-169`).
- `bench build` vs `bench watch` needed after editing `public/js/*.js` or `public/css/*.css` — hooks inject via `app_include_*`, not auto-reloaded.
- `pre-commit` `files: "nbs_customization.*"` only lints inside `apps/nbs_customization/nbs_customization/`; bench-level or `sites/` changes bypass hooks.
