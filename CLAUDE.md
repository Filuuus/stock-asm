# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Internal platform for Agropecuaria Santa María (GEA farm-equipment and dairy-hygiene distributor, Mexico), built on top of the company's Contpaqi ERP. UI text is Spanish; code and comments are English. See `README.md` for setup and the feature list.

## Hard rules

- **The ERP is read-only, always.** The credentials are read-only at the database level and no code may attempt a write. Anything the app needs to store goes in the local SQLite database through a Django app's own models.
- **The repo is public.** Never commit client, supplier or person names, or ERP ledger account names (vehicle accounts contain license plates). Store bare ERP ids and resolve names live from the ERP. The Excel/PDF files in the repo root are the owner's private reference material and are gitignored (`*.xlsx`, `*.xls`, `*.pdf`); never add them.
- **Verify against real data.** ERP column and account names are often misleading. Confirm what a field means by querying the live ERP (read-only) before relying on it.
- **Payroll and money rules are confirmed with management.** Commission rates, late-payment decay, category classification and payment-date resolution in `commissions/services.py` were agreed in several rounds with management; don't change them without the user re-confirming.

## Commands

Backend (Django, from `backend/`, venv at `backend/venv`):

```bash
venv/bin/python manage.py runserver 8000
venv/bin/python manage.py test                                    # all tests
venv/bin/python manage.py test analytics                          # one app
venv/bin/python manage.py test analytics.tests.SummarizeTests     # one class
venv/bin/python manage.py test analytics.tests.SummarizeTests.test_returns_net_and_ytd_windows
venv/bin/python manage.py migrate                                 # SQLite only; the router blocks the ERP
venv/bin/python manage.py export_corte_de_caja --year 2026 --month 9
```

Tests use made-up data only (mostly `SimpleTestCase` on the pure functions) and never connect to the ERP. To exercise real queries, use `manage.py shell` against the `erp` connection (needs `backend/.env` with the `DB_*` settings and the SQL Server ODBC driver).

A local **Redis** at `127.0.0.1:6379` is required: it's Django's cache (catalog, analytics, login throttling).

Frontend (Next.js 16 / React 19, from `frontend/`):

```bash
npm run dev          # http://localhost:3000, API at http://localhost:8000
npm run lint         # or: npx eslint components/analytics/SalesBIView.tsx
npx tsc --noEmit -p .   # type check (no npm script for it)
```

Next.js 16 has breaking changes from older versions: read the relevant guide in `frontend/node_modules/next/dist/docs/` before writing framework-level code (see `frontend/AGENTS.md`). There is no Prettier config, and the code is hand-formatted at ~120 columns: don't run Prettier over existing files.

`.claude/launch.json` has dev-server configs for both (`backend`, `frontend`).

## Architecture

**Two databases** (`backend/core/settings.py`): `default` is local SQLite with everything the app owns (accounts, roles, rates, overrides, adjustments, quote requests, product images); `erp` is the Contpaqi SQL Server. `api.routers.ERPRouter` sends the unmanaged `Adm*` models in `api/models.py` to `erp` and blocks migrations there. Contpaqi is really two databases on that server: **Comercial** (`adm*` tables: documents, line items, products, clients, agents), reached through the ORM models or raw SQL on `connections['erp']`, and **Contabilidad**, the accounting ledger (`MovimientosPoliza`, `Cuentas`, `Polizas`), reached with raw SQL using three-part names via `commissions.services.LEDGER_DATABASE`.

**One feature = one Django app**, each mounted under `/api/` in `core/urls.py`: `accounts` (session auth, roles, `/usuarios` self-service), `api` (the ERP model layer plus the product catalog/inventory endpoints), `catalog` (product images, cart and quote requests at `/api/solicitudes/`), `commissions`, `corte_de_caja`, `facturas`, `analytics`. Each app keeps its logic in `services.py` (queries plus pure functions) with thin DRF function views.

**`commissions/services.py` is the shared core.** It defines what counts as a real sale (`FACTURA_DOC_TYPE`, returns 5, credit notes 7, not cancelled, `ZONE_SCOPE` zones by `CIDAGENTE`), `CommissionRepository` (the scoped ERP reads), and payment-date resolution against the Contabilidad ledger (`attribute_ledger_payments`). `corte_de_caja` and `analytics` import these instead of redefining them, so changes there ripple into Comisiones, Corte de Caja and Ventas: re-check all three.

**Dates mean different things per source.** Sales are by Comercial invoice date (`CFECHA`), with returns and credit notes netted in the month they're issued. "Collected" is by the payment date recorded in Contabilidad: a payment only Comercial knows about doesn't count until it has a póliza. Receivables are Comercial's current `CPENDIENTE`. Income-statement and indicator numbers are by Contabilidad posting period (`Ejercicio`/`Periodo`), so they can legitimately differ from invoiced sales.

**`analytics` (the Ventas BI page)** runs its six ERP queries in parallel threads (each closes its own connections) and caches each month's response in Redis for 10 minutes. The cache key carries a version (`analytics_sales_vN_`): bump it whenever the response shape changes, or stale entries break the page. `?refresh=1` skips the cache. Expense categories come from ledger code sub-groups first and account-name words second (`EXPENSE_CATEGORIES`).

**Auth** is cookie-based Django sessions (no tokens). The browser and API run on different ports, so `CORS_ALLOW_CREDENTIALS` and `CSRF_TRUSTED_ORIGINS` are set for `localhost:3000`; they and the secure-cookie settings must change for a real deployment. Roles live on `accounts.Profile`: Vendedor, Contabilidad, Gerencia; a superuser counts as Gerencia. Gate views with `accounts.permissions` (`IsWorker`, `IsAccountingOrManagement`, `IsManagement`).

**Frontend**: App Router pages in `app/` are thin wrappers around client components in `components/<feature>/`. Every API call goes through `lib/api.ts` `apiFetch` (sends the session cookie and the CSRF header on mutating requests); the user and role come from `hooks/use-auth.tsx`. Use the same hostname for both servers (`localhost`, not `127.0.0.1`), or the session cookie isn't shared. Shared pieces: `components/ui` (shadcn), `components/sortable-table.tsx` (`HIDE_BELOW_SM`/`HIDE_BELOW_MD` responsive columns, `EmptyRow`), `components/date-controls.tsx` (`MonthControl`, `DateRangeControl`), `components/notice.tsx`, `lib/utils.ts` (`formatMoney`), `lib/zones.ts` (zone labels and order). Dates travel as `"YYYY-MM-DD"` / `"YYYY-MM"` strings and must be built with the helpers in `lib/dates.ts`, never `new Date("YYYY-MM-DD")` (that caused a real off-by-one-day bug).

## Product context

Users are office and sales staff plus management. Management reads its pages (Ventas, Comisiones) mainly on a tablet in landscape: keep table layouts there, test at about 1194×834, and save compact redesigns for phone widths (`sm:hidden` / `hidden sm:block`).
