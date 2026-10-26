# stock-asm

Internal platform for **Agropecuaria Santa María**, a GEA farm-equipment and dairy-hygiene distributor in Mexico. Built on top of the business's existing Contpaqi ERP (MSSQL) to give salespeople and management tools the ERP itself doesn't provide.

## Features

- **Product catalog** — live pricing and stock pulled from the ERP, with search, brand filtering, price range, sorting, and product images. Prices are private to logged-in workers by default; individual products can be marked public later without any role changes.
- **Sales commissions dashboard** (`/comisiones`) — automatically calculates commissions per salesman/zone from paid invoices, replacing a manually-maintained spreadsheet. Per-line-item category classification (Bionat / Refacciones / Servicios), late-payment decay, credit-note exclusion, payment-date resolution against the ERP's accounting ledger, and a management-only manual override tool (add a flat-amount correction or exclude an invoice, both auditable).
- **Corte de Caja dashboard** (`/corte-de-caja`) — automatic daily cash-collections log (one row per payment identified against a real invoice, including partial "abono" installments), replacing the accountant's manually-built "Corte de Caja Cobranza General" spreadsheet. Reuses commissions' own payment-date resolution against the ERP's accounting ledger, and additionally reads the ledger's bank-debit line to auto-suggest a payment method (Transferencia/Efectivo) per payment — the ERP has no real record of payment method beyond that, so this is a suggestion the accountant/manager confirms or corrects, not a guessed fact. A scheduled job can also regenerate a monthly `.xlsx` workbook (same day-by-day layout she's used to) onto a shared folder — see "Corte de Caja monthly export" below.
- **Rentabilidad** (`/rentabilidad`, management) — gross and net profit by zone, line, brand, product, client and month, combinable (e.g. Zona 2 × Bionat), with click-to-drill rows, search, invoice lists per product, year-over-year change and a monthly chart. Net = gross profit minus commissions (full possible or paid, switchable), import costs on imported products (switchable; the period's freight abroad, duties and brokers over its foreign-currency purchases, since Comercial's cost leaves them out), optionally supplier credit notes, and route costs: payroll (Contpaqi Nóminas), vehicle maintenance and LP fuel from the ledger, GPS km × km/L × price for other fuel, insurance and warehouse rent, spread by kg or by piece (switchable). Vehicle fuel and maintenance come from the accountant's monthly workbook where it covers the month (`python manage.py import_vehicle_reports`, reads `VEHICLE_REPORTS_DIR/<year>/Reportes Mensuales <year>.xlsx`; run it after each month closes), else from the ledger (maintenance, LP) and GPS km × km/L × price. Management edits the route-cost setup on the page (Gastos de ruta); GPS IMEIs are set locally only. Advance invoices and their applying credit notes are left out; other credit notes, which carry no product in the ERP, are spread over the invoice they were applied to. Kg per unit comes from the product name, the GEA catalog or an estimate, and management can type in a weight or exclude one-off products.
  - *Costs in dollars entered as pesos*: a sale line whose cost per unit is one of the product's dollar purchase prices is multiplied by that purchase's exchange rate, and an average cost dragged down by such lots is replaced by the latest dollar purchase at its rate (only when the result stays under the selling price). Goods with no usable cost are flagged "sin costo confiable".
  - *Left-out lines*: management can drop single invoice lines (gifts, promotions such as Buen Fin notes) and mark lines the supplier delivered directly, which carry no kg or route cost.
  - *Layout*: three sections (Resumen, Decisiones, Costos) under an always-visible Filtros bar (zona, línea, marca, search, product and client chips). "Ver detalle" adds the intermediate columns, "Criterios" sets the cost switches, and the browser remembers section, detail and criteria (`localStorage`).
  - *Decisiones*: the supplier discount each losing brand, line or product would need to break even, the concentration of contribution across products and clients, and a negotiation simulator (supplier discount, price or volume per brand, line or product; computed in the browser, not saved).
  - *PDF export* (print): pick the parts to include, a "sin montos" mode with sales and volume only for sharing outside, client names replaced by "Cliente 1, 2…", and optionally the selection compared with the rest of the business.
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

Run the tests (they use made-up data only and never connect to the ERP):

```bash
python manage.py test
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The app runs at `http://localhost:3000`, with the API at `http://localhost:8000/api/`.

A `.claude/launch.json` is included with dev-server configs for both.

### Fleet GPS log (Zeek → Notion)

Two commands copy the company vehicles' GPS trips from Zeek into a Notion database (the `fleet` app; no ERP involved), and a third keeps each unit's daily km in the local database:

```
python manage.py sync_fleet_log                     # yesterday; or --date 2026-10-06
python manage.py close_fleet_month                  # previous month; or --year 2026 --month 9
python manage.py store_fleet_km                     # yesterday; or --from 2026-10-02 --to 2026-10-09
```

`sync_fleet_log` writes one log entry per vehicle that moved (km, Google Maps route, one block per trip) and adds the km to the vehicle card's `Kilometraje`. `close_fleet_month` adds a `Reporte Mensual - <vehículo>` entry per vehicle (date, km and route link for each day) and then archives that month's daily entries to stay within Notion's limits; archived pages sit in Notion's trash for 30 days, after which the per-trip detail is gone. Both skip work already done, so re-running is safe. `store_fleet_km` saves each unit's km per day (0 if it didn't move) to `fleet.VehicleDayKm`, independent of Notion: it's the long-term record for fuel cost per route, since Zeek has no history before 2026-10-02. Schedule the first and third nightly and the second on the 1st.

Configuration goes in `backend/.env` (never in code, the repo is public):

```
ZEEK_TOKEN=
ZEEK_CLIENT=
ZEEK_LICENSE=
ZEEK_FLEET="IMEI=notion_vehicle_card_id;IMEI=notion_vehicle_card_id"
NOTION_TOKEN=
NOTION_FLEET_LOG_DB=
```

The Notion integration needs access to the log database and to every vehicle card. Details (Notion property names, scheduling) are in [`backend/fleet/README.md`](backend/fleet/README.md).

### Corte de Caja monthly export

`python manage.py export_corte_de_caja` regenerates this month's and last month's `.xlsx` workbooks (one sheet per business day, matching the layout the accountant used to build by hand) at `CORTE_DE_CAJA_EXPORT_DIR/<year>/Corte de Caja <year>-<month>.xlsx`. Last month is included because it keeps changing while late pólizas are posted. Every run fully overwrites the files with current data, so it's always safe to re-run. The sheets are protected (no password) so nobody types into a report by accident; changes go through the website. Refuses to generate anything before September 2026 (`corte_de_caja/exports.py::EARLIEST_EXPORT_MONTH`) — this replaces the manual process going forward, it doesn't backfill history.

```
python manage.py export_corte_de_caja                    # this month and last month
python manage.py export_corte_de_caja --year 2026 --month 9
```

Each day's sheet follows the accountant's own layout (same columns, fonts, borders, merged title and date, `TOTAL EFECTIVO`/`TERMINAL`/`CHEQUES`/`CORTE` block with live formulas), with rows grouped in blocks by zone, a transfers section outside `TOTAL CORTE`, and extra columns/totals the automatic version adds. Block headers use the ERP's own zone names (ZONA 1, OFICINA...); to show the salesperson's name instead, set `CORTE_DE_CAJA_ZONE_LABELS` in `backend/.env`, e.g. `CORTE_DE_CAJA_ZONE_LABELS="ZONA1=Nombre Apellido;ZONA2=Nombre Apellido"` (kept out of the code so real names never reach the repo).

`CORTE_DE_CAJA_EXPORT_DIR` defaults to a local `backend/exports/corte_de_caja/` folder for dev. On the office server it points at a folder on the file server mounted read-write at `/mnt/auto` (`Compartidos\Auto`, `deploy/install-auto-share.sh`; the Windows account should be able to write only there, and staff should only be able to read it). The `agrostma-corte-export` timer (installed by `deploy/install-services.sh`) runs the command every 15 minutes, Monday to Saturday 7:00–20:45, plus 23:30 every night; the Corte de Caja page's **Actualizar Excel** button (`POST /api/corte-de-caja/exportar/`) runs it on demand.

If someone has the file open in Excel when a run lands, Windows refuses to replace it: that month keeps its previous version (nothing gets corrupted), the run reports it (the button shows it as a warning), and the next run after the file is closed writes it. Excel doesn't reload an open file, so people see new numbers when they reopen it.
