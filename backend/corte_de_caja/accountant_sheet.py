"""Reads payment methods from the accountant's own Corte de Caja workbook.

The accountant still builds "Corte de caja <year>.xlsx" by hand every day
(one sheet per day, in the Contabilidad folder of the office file server's
Compartidos share; read-only mount on the server, see deploy/install-share.sh),
and its OBSERVACIONES column is where she writes how each payment came in.
The agrostma-corte-export timer (export_corte_de_caja) runs this import
before refreshing the exported workbooks, every 15 minutes; it stores what it
finds as CorteDeCajaAdjustment rows marked from_sheet, so the page and the
exports show it. It takes about 20 s (each day sheet parses in ~0.4 s), so
the page's "Actualizar Excel" button skips it.

Rules, agreed with the user 2026-11-20:
- Every "Corte de caja <year>*.xlsx" in CORTE_DE_CAJA_SHEET_DIR is read, so a
  new year's file or a split one ("Corte de caja 2025 (9-12).xlsx") needs no
  change. A sheet's day comes from its own date cell (C2), not its name; when
  two files have the same day, the most recently saved one wins.
- A sheet row matches a payment on the page by folio number and amount
  (within $1), on the nearest date up to MATCH_DAYS away (the sheet is dated
  when the money came in, Contabilidad often a day or two later, sometimes
  three weeks: Oct 9-12 payments posted Nov 1), preferring the same series.
  In Oct 1 - Nov 20 2026: 678 of 694 rows matched with 31 days (675 with 15);
  the rest were payments without a póliza yet, split amounts, rows she wrote
  twice, a reissued invoice and a $200 difference.
- A method set on the page always wins: the import only creates rows and
  updates the ones it created (from_sheet), and a page edit clears the flag.
- The workbook is only read, never written.
"""

import re
import zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import openpyxl
from django.conf import settings

from commissions.services import LEDGER_FULL_PAYMENT_TOLERANCE

from .models import CorteDeCajaAdjustment
from .services import calculate_corte_de_caja

MATCH_DAYS = 31
FOLIO = re.compile(r'^([A-Z])\s*-?\s*(\d+)$')  # 'B 20517', 'F-20908'

# OBSERVACIONES prefixes, from every note in the 2026 workbook (4,516 rows).
NOTE_METHODS = (
    ('TRANSF', CorteDeCajaAdjustment.PAYMENT_METHOD_TRANSFERENCIA),  # TRANSFERENCIA BBVA, typos TRANSFERERENCIA...
    ('TRASF', CorteDeCajaAdjustment.PAYMENT_METHOD_TRANSFERENCIA),
    ('TERM', CorteDeCajaAdjustment.PAYMENT_METHOD_TERMINAL),  # TERMINAL D (débito) / CR (crédito), TERMINAR CR
    ('CH', CorteDeCajaAdjustment.PAYMENT_METHOD_CHEQUE),  # CH-1012 ST, CH-1163 BBVA POSTF 12 ENE 26 (post-dated)
    ('EFECTIVO', CorteDeCajaAdjustment.PAYMENT_METHOD_EFECTIVO),  # EFECTIVO BBVA: cash deposited at that bank
)


def note_method(note):
    """The payment method an OBSERVACIONES note means. Blank is cash: the
    sheet's own TOTAL EFECTIVO is TOTAL CORTE minus terminal and cheques.
    None for anything else (in 2026 only 'SALVO BUEN COBRO', once)."""
    note = (note or '').strip().upper()
    if not note:
        return CorteDeCajaAdjustment.PAYMENT_METHOD_EFECTIVO
    return next((method for prefix, method in NOTE_METHODS if note.startswith(prefix)), None)


def read_day_sheet(rows):
    """(day, [(series, folio, amount, note)]) from one day sheet's rows
    (values only, columns A-K): the date in C2, then every row with a
    'B 20517'-style No. FACTURA and a number in HABER. Read to the end: on a
    busy day she starts a second page under the TOTAL rows (29 Sep 2026: 24
    payments there). Rows without a usable folio ('F', 'DEV',
    'F 19947-19948') can't be matched and are skipped."""
    day, payments = None, []
    for number, row in enumerate(rows, start=1):
        row = tuple(row) + (None,) * (11 - len(row))
        if number == 2:
            day = row[2].date() if isinstance(row[2], datetime) else None
        folio = FOLIO.match(str(row[2] or '').strip().upper())
        if folio and isinstance(row[4], (int, float)):
            payments.append((folio[1], int(folio[2]), Decimal(str(round(row[4], 2))), str(row[10] or '').strip()))
    return day, payments


def read_workbooks(folder, first_day, last_day):
    """{day: payments} for the days in [first_day, last_day], from every
    'Corte de caja <year>*.xlsx' in `folder`, oldest file first so the most
    recently saved one wins a day both have. Only those days' sheets are read
    in full (dates from C2 alone take half a second for the 229 sheets of 2026)."""
    paths = sorted(
        (path for year in range(first_day.year, last_day.year + 1)
         for path in Path(folder).glob(f'Corte de caja {year}*.xlsx')),
        key=lambda path: path.stat().st_mtime,
    )
    by_day = {}
    for path in paths:
        book = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            for ws in book.worksheets:
                day, _ = read_day_sheet(ws.iter_rows(max_row=2, max_col=11, values_only=True))
                if not (day and first_day <= day <= last_day):
                    continue
                _, payments = read_day_sheet(ws.iter_rows(max_col=11, values_only=True))
                if payments:  # she keeps empty sheets ready for the coming days
                    by_day[day] = payments
        finally:
            book.close()
    return by_day


def match_payments(sheet_payments, corte_rows):
    """[(Corte de Caja row, note)]: each sheet payment (day, series, folio,
    amount, note) paired with at most one row of calculate_corte_de_caja,
    and each row used once (see the module docstring for the rule)."""
    rows_by_folio = defaultdict(list)
    for row in corte_rows:
        rows_by_folio[int(row['folio'])].append(row)
    taken, pairs = set(), []
    for day, series, folio, amount, note in sorted(sheet_payments, key=lambda payment: payment[0]):  # sheet order within a day
        candidates = [
            row for row in rows_by_folio[folio]
            if id(row) not in taken
            and abs(row['amount'] - amount) < LEDGER_FULL_PAYMENT_TOLERANCE
            and abs((row['event_date'] - day).days) <= MATCH_DAYS
        ]
        if candidates:
            best = min(candidates, key=lambda row: (
                not row['folio_display'].startswith(f'{series} '), abs((row['event_date'] - day).days),
            ))
            taken.add(id(best))
            pairs.append((best, note))
    return pairs


def import_accountant_sheet(today=None):
    """Imports last month's and this month's days, the months the export
    refreshes. Returns a one-line summary; an unset folder or an unreadable
    file (e.g. caught mid-save) is reported, not raised, so the export runs
    anyway."""
    folder = settings.CORTE_DE_CAJA_SHEET_DIR
    if not folder:
        return 'Hoja de Contabilidad: falta CORTE_DE_CAJA_SHEET_DIR, no se leyó.'
    today = today or date.today()
    first_day = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    try:
        by_day = read_workbooks(folder, first_day, today)
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        return f'Hoja de Contabilidad: no se pudo leer ({exc}).'
    sheet_payments = [(day, *payment) for day, payments in by_day.items() for payment in payments]
    pairs = match_payments(sheet_payments, calculate_corte_de_caja(first_day - timedelta(days=MATCH_DAYS), today)['rows'])

    existing = {
        (a.invoice_id, a.event_date): a
        for a in CorteDeCajaAdjustment.objects.filter(invoice_id__in={row['invoice_id'] for row, _ in pairs})
    }
    created = updated = 0
    for row, note in pairs:
        method = note_method(note)
        if method is None:
            continue
        fields = {
            'payment_method': method,
            # Only a cheque's note says more than the method and bank already do (number, bank, post-dated).
            'note': note.upper()[:200] if method == CorteDeCajaAdjustment.PAYMENT_METHOD_CHEQUE else '',
            'client_id': row['client_id'],
            'bank_code': row['bank_code'],
        }
        adjustment = existing.get((row['invoice_id'], row['event_date']))
        if adjustment is None:
            CorteDeCajaAdjustment.objects.create(
                invoice_id=row['invoice_id'], event_date=row['event_date'], from_sheet=True, **fields,
            )
            created += 1
        elif adjustment.from_sheet and any(getattr(adjustment, k) != v for k, v in fields.items()):
            for field, value in fields.items():
                setattr(adjustment, field, value)
            adjustment.save()
            updated += 1
    # ponytail: a row the accountant deletes from her sheet keeps its imported method; clear it on the page.
    return (f'Hoja de Contabilidad: {len(sheet_payments)} pagos leídos, {len(pairs)} encontrados en el corte, '
            f'{created} nuevos, {updated} actualizados.')
