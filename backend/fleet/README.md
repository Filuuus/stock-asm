# Fleet GPS log (Zeek GPS → Notion)

Copies the trip history of each company vehicle from the Zeek GPS API into a Notion workspace: one log entry per vehicle per day, a running odometer on each vehicle's card, and a monthly summary per vehicle. It replaces the manual mileage log.

Based on Emmanuel Alcalá's original standalone scripts (`rastreo_zeek.py`, `cierre_mensual.py`), now Django management commands. Naming each stop after the client there is also his idea (his `feature/fleet-gps` branch matched stops to the Notion client list within 100 m); here it uses the saved places in the local database and the same rules as the route-sheet reviews. The app reads Zeek and writes Notion, plus daily km and stops per unit to the local database; from the ERP it only reads client names.

## What it does

**`sync_fleet_log`** (daily), for each vehicle that moved that day:

- Reads its trips from Zeek and splits them into legs of driving between stops (`timeline.py`). Zeek ends a trip only when the ignition goes off, so a stop with the engine left running (a salesman who keeps the truck idling at a client) is found in the trip's GPS points instead: 3 minutes or more at 3 km/h or less, within 60 m. A truck idling before it's turned off arrives when it stopped moving.
- Creates an entry in the log database with the day's km, the updated odometer, a Google Maps link with the day's route through its parked stops (up to 20 points) and one callout per leg, marked like a traffic light: 🟢 leaving a parked spot, 🟡 an engine-on stop (it ends one leg and starts the next, with how long the engine ran), 🔴 the ignition off. Each has a map link to where it stopped and, when it's known, what that place is (`matching.py`): 👤 the clients of a saved place within 300 m (all of them when a family farm is several clients), 🏢 a company site within 400 m, or 📌 a spot someone identified within 150 m ("Parada personal" for a home). Client names come live from the ERP (read-only).
- Adds the day's km to the `Kilometraje` property of the vehicle's card.

**`close_fleet_month`** (monthly), for each vehicle:

- Adds up its daily entries for the month into one `Reporte Mensual - <vehicle>` entry: total km, final odometer, the month as a date range, and one line per day with its km and route link.
- Then archives that month's daily entries to stay within Notion's limits. Archived pages go to Notion's trash, which empties after 30 days, so after that only the monthly summary is left. The per-trip times and destinations are gone.

Both commands are safe to re-run:

- `sync_fleet_log` skips vehicles that already have an entry for that day, so the odometer is never added twice. `--rewrite --date D [--vehicle NAME]` redoes an existing day's callouts and route link from Zeek (only while Zeek still has the day), and `--refresh-names [--date D]` re-names the stops on that month's pages from the saved places as they are now (a pin fixed, a spot identified later). Neither touches km or odometers.
- `close_fleet_month` skips vehicles that already have that month's report, and archives a vehicle's daily entries only after its report exists.

Nothing is lost when a month is closed: before archiving, `close_fleet_month` copies every daily page's km and stops into the local database (as `store_fleet_km --from-notion` does), and it archives a page only if that vehicle's day is stored locally. Pages it can't match (a vehicle name with no card) stay in Notion, and the log says so.

**`build_route_sheets`** (nightly, after `store_fleet_km`) writes the month's route sheets to `ROUTE_SHEETS_EXPORT_DIR/<year>/Hojas de ruta YYYY-MM.xlsx` (the shared Auto folder on the server), up to yesterday, and rebuilds the whole month each night so the day before picks up the invoices entered that morning (`route_sheets.py`):

- **ZONA 1 / ZONA 2**: each salesman's day, from the truck whose stops that zone invoiced (one truck per salesman per day). Every stop with its client (only the clients of a shared place who were invoiced from the day before to two days after, all of them when none were), sale and folios, or what the place is; unknown stops under 3 minutes are left out as driving pauses, longer ones suggest clients invoiced around that day whose town is within 6 km.
- **SERVICIOS**: the service crew's day (`FLEET_SERVICE_IMEI`, or another truck on a day the crew's truck visited none of its calendar's clients and that one did), with each stop's activity from the crew's Notion calendar (`NOTION_SERVICE_TASKS_DB`) and its service invoice (product `0000 SERVICIO` / `0004 SERVICIO DE EMERGENCIA` from the SERVICIOS agent, or with no part description, since `0000` is also a generic code for parts). Calendar tasks with no stop are listed under the day.
- **OTRAS UNIDADES**: every other truck's day. **PENDIENTES**: the stops nobody has identified yet; the answers are saved as places (`kind='spot'`) and show up from the next run.

Names come live from the ERP and the saved places. The paper route sheets, when scanned, are still compared by hand (`reportes/`).

## Notion setup

1. Create an integration at [Notion Developers](https://www.notion.so/my-integrations) with read and write access.
2. Invite it to the log database and to every vehicle card.

The code expects these property names, exactly as written:

| Where | Property | Type |
|---|---|---|
| Log database | `Vehículo` | Title |
| | `Fecha` | Date |
| | `Recorrido Diario` | Number |
| | `Kilometraje Total` | Number |
| | `Ruta` | URL |
| Vehicle card | (its title) | Title, used as the vehicle name in the log |
| | `Kilometraje` | Number, the running odometer |

## Configuration

Everything goes in `backend/.env`, never in code: the repo is public, and that includes the fleet's GPS IMEIs and Notion ids.

```env
ZEEK_TOKEN=
ZEEK_CLIENT=
ZEEK_LICENSE=
ZEEK_FLEET="IMEI=notion_vehicle_card_id;IMEI=notion_vehicle_card_id"
NOTION_TOKEN=
NOTION_FLEET_LOG_DB=
NOTION_SERVICE_TASKS_DB=      # the service crew's calendar (Tareas)
FLEET_SERVICE_IMEI=           # the service crew's GPS unit
ROUTE_SHEETS_EXPORT_DIR=      # where build_route_sheets writes (the shared Auto folder)
```

`ZEEK_FLEET` lists each vehicle's GPS unit IMEI (the Zeek unit id) and its Notion card's page id, separated by `;`. To add a vehicle, create its card in Notion, invite the integration to it, and add an `IMEI=page_id` pair.

The page id is the 32-character hex string at the end of the card's URL. Nothing beyond the backend's own requirements needs to be installed, since Zeek and Notion are called with the standard library.

## Usage

From `backend/`:

```bash
venv/bin/python manage.py sync_fleet_log                       # yesterday
venv/bin/python manage.py sync_fleet_log --date 2026-10-06     # a specific day, e.g. to fill a gap
venv/bin/python manage.py sync_fleet_log --rewrite --date 2026-11-18 --vehicle "Hilux 1"
venv/bin/python manage.py sync_fleet_log --refresh-names       # this month's pages, names from the saved places
venv/bin/python manage.py close_fleet_month                    # previous month
venv/bin/python manage.py close_fleet_month --year 2026 --month 9
venv/bin/python manage.py store_fleet_km                       # yesterday's km per unit into the local DB
venv/bin/python manage.py store_fleet_km --from 2026-10-02 --to 2026-10-09
venv/bin/python manage.py store_fleet_km --from-notion         # rescue stops of days Zeek no longer has
venv/bin/python manage.py build_route_sheets                   # this month's route sheets (--year/--month for another)
```

`store_fleet_km` reads Zeek directly (not Notion) and saves each unit's km per day in `VehicleDayKm`, 0 when it didn't move, and its stops (where each leg ended, until it moved on; `engine_on` for the stops inside a trip) in `VehicleStop`; a unit Zeek fails to answer for gets no row, so gaps show. Re-running replaces a stored day only with at least as many km: Zeek sometimes answers with no trips, or only part of the day, for a unit that did move (a late upload, or a day already trimming out of its window), and that must not erase what's stored. **Zeek keeps only about the last six days**, so these tables are the only long-term record: run it at least every few days. For days Zeek has already dropped, `--from-notion` reads the stops from the daily log pages instead (only until `close_fleet_month` archives them), leaving days already stored from Zeek alone.

On the office server these run from systemd timers in `deploy/` (installed by `deploy/install-services.sh`): `store_fleet_km`, `build_route_sheets` and `sync_fleet_log` every night at 00:10 for the day that just ended, re-checking the day before for trips Zeek reported late, and `close_fleet_month` on the 1st at 01:00, after the daily job has logged the month's last day. A trip still under way at that hour (a late emergency call) isn't finished when the day is logged. The next night's re-check adds a vehicle Zeek hadn't reported at all and updates the local km to the fuller number, but a vehicle already logged in Notion for that day isn't rewritten there. A run missed while the server was off happens when it's back. Logs: `journalctl -u agrostma-fleet-daily` (or `-monthly`).

Only one copy may write the Notion log: `sync_fleet_log` skips vehicles already logged that day, but another script that doesn't check would add the same day twice and double the odometer.

Days are calendar days in Mexico's fixed UTC-6. Mexico has had no daylight saving time since 2022.

## Code

- `zeek.py`: the Zeek API and its coordinate and time formats.
- `timeline.py`: a day's trips as legs and stops, including the engine-on ones.
- `matching.py`: what a stop was, from `profitability.SavedPlace`: client places, company sites (`kind='base'`) and identified spots (`kind='spot'`, `personal` for homes). Bookmarks nobody checked and town-level pins never name a stop. The route-sheet reviews use the same matcher.
- `notion.py`: the Notion API, the daily page's callouts, and reading them back into stops (old pages without 🟡 read the same way).
- `route_sheets.py`: the monthly route sheets (ZONA 1, ZONA 2, SERVICIOS, OTRAS UNIDADES, PENDIENTES).
- `services.py`: the jobs (local km and stops, the daily Notion log and its rewrite and re-naming, the monthly close).
- `management/commands/`: the three commands.
- `tests.py`: covers coordinate and time parsing, legs and engine-on stops, naming, writing and reading back callouts, and the monthly close's archive order. It uses made-up data and never calls Zeek, Notion or the ERP.
