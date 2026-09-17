# stock-asm

Internal platform for **Agropecuaria Santa María**, a GEA farm-equipment and dairy-hygiene distributor in Mexico. Built on top of the business's existing Contpaqi ERP (MSSQL) to give salespeople and management tools the ERP itself doesn't provide.

## Features

- **Product catalog** — live pricing and stock pulled from the ERP, with search, brand filtering, price range, sorting, and product images.
- **Sales commissions dashboard** (`/comisiones`) — automatically calculates commissions per salesman/zone from paid invoices, replacing a manually-maintained spreadsheet. Per-line-item category classification (Bionat / Refacciones / Servicios), late-payment decay, credit-note exclusion, and payment-date resolution against the ERP's accounting ledger.

## Architecture

- **Backend** — Django (`backend/`), split into `api` (the read-only ERP layer), `catalog`, and `commissions`, following a "one feature = one app" pattern.
- **Frontend** — Next.js App Router (`frontend/`).
- **Database** — two connections: a local SQLite database (`default`) owns all app-created data (product images, commission rate config), and a read-only connection to the Contpaqi MSSQL ERP (`erp`). A database router hard-blocks Django migrations from ever running against the ERP.

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

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The app runs at `http://localhost:3000`, with the API at `http://localhost:8000/api/`.

A `.claude/launch.json` is included with dev-server configs for both.
