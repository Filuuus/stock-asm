# stock-asm

Internal platform for **Agropecuaria Santa María**, a GEA farm-equipment and dairy-hygiene distributor in Mexico. Built on top of the business's existing Contpaqi ERP (MSSQL) to give salespeople and management tools the ERP itself doesn't provide.

## Features

- **Product catalog** — live pricing and stock pulled from the ERP, with search, brand filtering, price range, sorting, and product images. Prices are private to logged-in workers by default; individual products can be marked public later without any role changes.
- **Sales commissions dashboard** (`/comisiones`) — automatically calculates commissions per salesman/zone from paid invoices, replacing a manually-maintained spreadsheet. Per-line-item category classification (Bionat / Refacciones / Servicios), late-payment decay, credit-note exclusion, payment-date resolution against the ERP's accounting ledger, and a management-only manual override tool (add a flat-amount correction or exclude an invoice, both auditable).
- **Access control** — plain username/password accounts (no SSO, no self-signup; not everyone has a company email). Two roles: **Vendedor** (salesperson) and **Gerencia** (management, which also gets the commission override tool). Management manages accounts themselves at `/usuarios` — create, reset passwords, activate/deactivate, with a full audit log — no Django admin access needed day-to-day.

## Architecture

- **Backend** — Django (`backend/`), split into `api` (the read-only ERP layer), `accounts` (auth, roles, self-service user management), `catalog`, and `commissions`, following a "one feature = one app" pattern.
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
