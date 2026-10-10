"""Reads the accountant's monthly vehicle workbook ("Reportes Mensuales <year>.xlsx", on the
accounting share): fuel per vehicle per month (sheet Combustible) and maintenance per vehicle per
month (sheet Mantenimiento de Vehículos). Management treats it as ground truth for both (2026-10-10):
the ledger has a single fuel account and books part of the maintenance elsewhere.

Layout quirks handled (checked on the 2024-2026 files): every month is a block with its own title
("ENERO 2026") and its own vehicle header row, whose columns move between years ("F 350" / "F350",
the forklift as "ALMACEN"); the month total is the row labelled exactly "TOTAL" (weekly ones say
"TOTAL SEMANAL"). Unused blocks at the end of a file are copies of last year's with last year's
titles, and the current month is half filled, so only blocks titled with the file's year and before
`before` are read. Maintenance rows carry their own date, which is used instead of the block title
(a "FEBRERO 2024" block sits in the 2025 file)."""
import re
from collections import defaultdict
from datetime import datetime

MONTHS = ['ENERO', 'FEBRERO', 'MARZO', 'ABRIL', 'MAYO', 'JUNIO', 'JULIO', 'AGOSTO', 'SEPTIEMBRE', 'OCTUBRE',
          'NOVIEMBRE', 'DICIEMBRE']
TITLE_RE = re.compile(rf"^({'|'.join(MONTHS)})\s+(\d{{4}})$")
# Sheet spellings of the same vehicle.
ALIASES = {'ALMACEN': 'MONTACARGAS', 'FIAT3': 'FIAT', 'SEATTARRACO': 'TARRACO'}
HEADER_MARKERS = {'HILUX1', 'TARRACO'}


def vehicle_key(name):
    """'F 350' / 'F350' -> 'F350', 'ALMACEN' -> 'MONTACARGAS': the name PoolVehicle.sheet_name holds."""
    key = re.sub(r'\s+', '', str(name or '')).upper()
    return ALIASES.get(key, key)


def parse_fuel(rows, year, before):
    """{('YYYY-MM', vehicle): pesos} from the Combustible sheet's rows (tuples of cell values).
    Every vehicle of a read month gets an entry, zeros included, so the month counts as covered."""
    out, month, header = {}, None, {}
    for row in rows:
        first = row[0].strip() if isinstance(row[0], str) else row[0]
        match = TITLE_RE.match(first) if isinstance(first, str) else None
        if match:
            m = f'{match.group(2)}-{MONTHS.index(match.group(1)) + 1:02d}'
            month = m if int(match.group(2)) == year and m < before else None
            header = {}
            continue
        if month and not header and HEADER_MARKERS & {vehicle_key(c) for c in row if isinstance(c, str)}:
            header = {i: vehicle_key(c) for i, c in enumerate(row) if isinstance(c, str) and c.strip()}
        elif month and header and first == 'TOTAL':
            for i, vehicle in header.items():
                value = row[i] if i < len(row) else None
                out[(month, vehicle)] = round(float(value), 2) if isinstance(value, (int, float)) else 0.0
            month = None
    return out


def parse_maintenance(rows, year, before):
    """{('YYYY-MM', vehicle): pesos before IVA} from the Mantenimiento sheet, by each row's date."""
    out = defaultdict(float)
    for row in rows:
        if len(row) < 6:
            continue
        day, vehicle, amount = row[0], row[1], row[5]
        if not isinstance(day, datetime) or not vehicle:
            continue
        month = f'{day:%Y-%m}'
        try:
            value = float(amount)
        except (TypeError, ValueError):
            continue
        if day.year == year and month < before:
            out[(month, vehicle_key(vehicle))] += value
    return {k: round(v, 2) for k, v in out.items()}
