# stock-asm

Internal platform for **Agropecuaria Santa María**, a GEA farm-equipment and dairy-hygiene distributor in Mexico. Built on top of the business's existing Contpaqi ERP (MSSQL) to give salespeople and management tools the ERP itself doesn't provide.

## Features

- **Product catalog** — live pricing and stock pulled from the ERP, with search, brand filtering, price range, sorting, and product images. Prices are private to logged-in workers by default; individual products can be marked public later without any role changes.
- **Sales commissions dashboard** (`/comisiones`) — automatically calculates commissions per salesman/zone from paid invoices, replacing a manually-maintained spreadsheet. Per-line-item category classification (Bionat / Refacciones / Servicios), late-payment decay, credit-note exclusion, payment-date resolution against the ERP's accounting ledger, and a management-only manual override tool (add a flat-amount correction or exclude an invoice, both auditable).
- **Corte de Caja dashboard** (`/corte-de-caja`) — automatic daily cash-collections log (one row per payment identified against a real invoice, including partial "abono" installments), replacing the accountant's manually-built "Corte de Caja Cobranza General" spreadsheet. Reuses commissions' own payment-date resolution against the ERP's accounting ledger, and additionally reads the ledger's bank-debit line to auto-suggest a payment method (Transferencia/Efectivo) per payment — the ERP has no real record of payment method beyond that, so this is a suggestion the accountant/manager confirms or corrects, not a guessed fact. A scheduled job can also regenerate a monthly `.xlsx` workbook (same day-by-day layout she's used to) onto a shared folder — see "Corte de Caja monthly export" below.
- **Access control** — plain username/password accounts (no SSO, no self-signup; not everyone has a company email). Three roles: **Vendedor** (salesperson), **Contabilidad** (accounting/office staff — Corte de Caja access), and **Gerencia** (management — everything, plus the commission override tool). Management manages accounts themselves at `/usuarios` — create, reset passwords, activate/deactivate, with a full audit log — no Django admin access needed day-to-day.

## Architecture

- **Backend** — Django (`backend/`), split into `api` (the read-only ERP layer), `accounts` (auth, roles, self-service user management), `catalog`, `commissions`, and `corte_de_caja`, following a "one feature = one app" pattern.
- **Frontend** — Next.js App Router (`frontend/`).
- **Database** — two connections: a local SQLite database (`default`) owns all app-created data (product images, commission rate config, accounts), and a read-only connection to the Contpaqi MSSQL ERP (`erp`). A database router hard-blocks Django migrations from ever running against the ERP.
- **Auth** — cookie-based Django sessions (not tokens), chosen for the simplest possible login UX. The browser and API run on different ports even in dev, so this needs `CORS_ALLOW_CREDENTIALS` and `CSRF_TRUSTED_ORIGINS` set correctly (`backend/core/settings.py`) — both are currently hardcoded to `localhost:3000`/`127.0.0.1:3000` and **will need updating for any real deployment**, along with turning on `SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE` once this is served over HTTPS.

**Hard constraint: the ERP is read-only, always.** The ERP credentials are genuinely read-only at the database level, and no code in this repo should ever attempt to write to it. Any new feature needing its own storage adds tables to the local SQLite database via a new Django app instead.

## Getting started

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create `backend/.env` with the ERP connection details:

```
DB_NAME=
DB_HOST=
DB_PORT=
DB_USER=
DB_PASSWORD=
```

The SQL Server ODBC driver defaults to `ODBC Driver 18 for SQL Server`. If the machine has a different version installed (e.g. 17), set `DB_DRIVER` in `.env` to match its exact name instead of installing another one (`odbcinst -q -d` lists installed drivers on macOS/Linux; on Windows check ODBC Data Sources → Drivers):

```
DB_DRIVER=ODBC Driver 17 for SQL Server
```

Then run migrations (against the local SQLite database only) and start the server:

```bash
python manage.py migrate
python manage.py runserver 8000
```

Create the first account — a Django superuser automatically has full Gerencia (management) access:

```bash
python manage.py createsuperuser
```

Log in at `/login` with those credentials, then use `/usuarios` to create real accounts for the rest of the team. No further Django admin/shell access should be needed for day-to-day account management after that.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The app runs at `http://localhost:3000`, with the API at `http://localhost:8000/api/`.

A `.claude/launch.json` is included with dev-server configs for both.

### Corte de Caja monthly export

`python manage.py export_corte_de_caja` regenerates that month's `.xlsx` workbook (one sheet per business day, matching the layout the accountant used to build by hand) at `CORTE_DE_CAJA_EXPORT_DIR` — every run fully overwrites the file with current data, so it's always safe to re-run. Refuses to generate anything before September 2026 (`corte_de_caja/exports.py::EARLIEST_EXPORT_MONTH`) — this replaces the manual process going forward, it doesn't backfill history.

```
python manage.py export_corte_de_caja                    # current month
python manage.py export_corte_de_caja --year 2026 --month 9
```

Set `CORTE_DE_CAJA_EXPORT_DIR` in `backend/.env` to wherever this should land — defaults to a local `backend/exports/corte_de_caja/` folder, which is fine for dev but not what the accountant should actually open. In production it should point at a real folder on the (Windows) server that's shared out over SMB, so opening the file is exactly as before, just without the manual build step:

1. Pick/create a folder on the server and share it over SMB the normal Windows way (Properties → Sharing) — this is a one-time server/IT step, not something the app does.
2. Set `CORTE_DE_CAJA_EXPORT_DIR` to that folder's local path (e.g. `C:\Shares\CorteDeCaja`) so Django writes directly into the shared folder.
3. Schedule `python manage.py export_corte_de_caja` to run periodically (Windows Task Scheduler; hourly is a reasonable starting cadence) so the file stays current without anyone triggering it by hand.

If the accountant has the file open in Excel when a scheduled run lands, Windows may refuse to overwrite it (a held file lock) — the run fails safely (nothing gets corrupted) and picks back up on the next scheduled run once she's closed it.
