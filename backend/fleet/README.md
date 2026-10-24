# Fleet GPS log (Zeek GPS → Notion)

Copies the trip history of each company vehicle from the Zeek GPS API into a Notion workspace: one log entry per vehicle per day, a running odometer on each vehicle's card, and a monthly summary per vehicle. It replaces the manual mileage log.

Based on Emmanuel Alcalá's original standalone scripts (`rastreo_zeek.py`, `cierre_mensual.py`), now two Django management commands. The app reads Zeek and writes Notion, plus daily km per unit to the local database; it never touches the ERP.

## What it does

**`sync_fleet_log`** (daily), for each vehicle that moved that day:

- Reads its trips from Zeek: start and end time, distance, duration and destination (the Zeek geofence name when there is one).
- Builds one Google Maps link with the day's whole route (up to 20 stops) plus a map link for each stop.
- Creates an entry in the log database with the day's km, the updated odometer, the route link and one block per trip.
- Adds the day's km to the `Kilometraje` property of the vehicle's card.

**`close_fleet_month`** (monthly), for each vehicle:

- Adds up its daily entries for the month into one `Reporte Mensual - <vehicle>` entry: total km, final odometer, the month as a date range, and one line per day with its km and route link.
- Then archives that month's daily entries to stay within Notion's limits. Archived pages go to Notion's trash, which empties after 30 days, so after that only the monthly summary is left. The per-trip times and destinations are gone.

Both commands are safe to re-run:

- `sync_fleet_log` skips vehicles that already have an entry for that day, so the odometer is never added twice.
- `close_fleet_month` skips vehicles that already have that month's report, and archives a vehicle's daily entries only after its report exists.

Nothing is lost when a month is closed: before archiving, `close_fleet_month` copies every daily page's km and stops into the local database (as `store_fleet_km --from-notion` does), and it archives a page only if that vehicle's day is stored locally. Pages it can't match (a vehicle name with no card) stay in Notion, and the log says so.

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
```

`ZEEK_FLEET` lists each vehicle's GPS unit IMEI (the Zeek unit id) and its Notion card's page id, separated by `;`. To add a vehicle, create its card in Notion, invite the integration to it, and add an `IMEI=page_id` pair.

The page id is the 32-character hex string at the end of the card's URL. Nothing beyond the backend's own requirements needs to be installed, since Zeek and Notion are called with the standard library.

## Usage

From `backend/`:

```bash
venv/bin/python manage.py sync_fleet_log                       # yesterday
venv/bin/python manage.py sync_fleet_log --date 2026-10-06     # a specific day, e.g. to fill a gap
venv/bin/python manage.py close_fleet_month                    # previous month
venv/bin/python manage.py close_fleet_month --year 2026 --month 9
venv/bin/python manage.py store_fleet_km                       # yesterday's km per unit into the local DB
venv/bin/python manage.py store_fleet_km --from 2026-10-02 --to 2026-10-09
venv/bin/python manage.py store_fleet_km --from-notion         # rescue stops of days Zeek no longer has
```

`store_fleet_km` reads Zeek directly (not Notion) and saves each unit's km per day in `VehicleDayKm`, 0 when it didn't move, and its stops (each trip's end, until the next trip starts) in `VehicleStop`; a unit Zeek fails to answer for gets no row, so gaps show. Re-running replaces a stored day only with at least as many km: Zeek sometimes answers with no trips, or only part of the day, for a unit that did move (a late upload, or a day already trimming out of its window), and that must not erase what's stored. **Zeek keeps only about the last six days**, so these tables are the only long-term record: run it at least every few days. For days Zeek has already dropped, `--from-notion` reads the stops from the daily log pages instead (only until `close_fleet_month` archives them), leaving days already stored from Zeek alone.

On the office server these run from systemd timers in `deploy/` (installed by `deploy/install-services.sh`): `store_fleet_km` then `sync_fleet_log` every night at 00:10 for the day that just ended, re-checking the day before for trips Zeek reported late, and `close_fleet_month` on the 1st at 01:00, after the daily job has logged the month's last day. A trip still under way at that hour (a late emergency call) isn't finished when the day is logged. The next night's re-check adds a vehicle Zeek hadn't reported at all and updates the local km to the fuller number, but a vehicle already logged in Notion for that day isn't rewritten there. A run missed while the server was off happens when it's back. Logs: `journalctl -u agrostma-fleet-daily` (or `-monthly`).

Only one copy may write the Notion log: `sync_fleet_log` skips vehicles already logged that day, but another script that doesn't check would add the same day twice and double the odometer.

Days are calendar days in Mexico's fixed UTC-6. Mexico has had no daylight saving time since 2022.

## Code

- `services.py`: the Zeek and Notion calls and the summary logic.
- `management/commands/`: the three commands.
- `tests.py`: covers coordinate and time parsing, the daily and monthly summaries, and the monthly close's archive order. It uses made-up data and never calls Zeek or Notion.
