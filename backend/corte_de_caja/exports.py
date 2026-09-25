"""Generates the monthly Corte de Caja workbook - an automatically
regenerated replacement for the accountant's manually-built spreadsheet,
written to a shared folder so she can keep opening it the same way she
always has instead of using the web dashboard directly (requested
2026-09-24, see the corte-de-caja-dashboard project memory).

Structure mirrors the real "Corte de caja 2026.xlsx" as closely as the
automatically-derived data supports: one sheet per business day that had at
least one payment, same header row/column order (CUENTA, NOMBRE DEL
CLIENTE, No. FACTURA, DEBE, HABER, ENTREGA, RECIBE, VENCIMIENTO, COMISION,
EQ-R-S, OBSERVACIONES), plus two new trailing columns (FORMA DE PAGO,
BANCO) for the payment-method suggestion the web dashboard now tracks.
CUENTA/ENTREGA/RECIBE are left blank - their meaning was never decoded (see
that memory) and guessing would be worse than an honestly empty cell.

Two deliberate differences from the original, both already decided with
the user when the web dashboard was built:
- No per-salesperson "who collected it" block/subtotal grouping - not
  derivable from the ERP. Zone subtotal rows stand in for it.
- OBSERVACIONES holds only the accountant's own note; the payment method
  goes in its own new column instead of being folded into free text.

Like the web dashboard, this only ever reads from the ERP + this app's own
CorteDeCajaAdjustment table - the old spreadsheet is never read as an input.
"""

import calendar
from datetime import date
from pathlib import Path

from django.conf import settings
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from api.models import AdmConceptos, AdmDocumentos
from corte_de_caja.models import CorteDeCajaAdjustment
from corte_de_caja.services import calculate_corte_de_caja

# No workbook is ever generated for a month before this one - the user was
# explicit (2026-09-24) that this replaces the manual process going
# forward, not a backfill of it.
EARLIEST_EXPORT_MONTH = date(2026, 9, 1)

HEADERS = [
    'CUENTA', 'NOMBRE DEL CLIENTE', 'No. FACTURA', 'DEBE', 'HABER', 'ENTREGA', 'RECIBE',
    'VENCIMIENTO', 'COMISION', 'EQ-R-S', 'OBSERVACIONES', 'FORMA DE PAGO', 'BANCO',
]

ZONE_SHEET_CODES = {
    'ZONA1': 'Z-1', 'ZONA2': 'Z-2', 'OFICINA': 'O', 'SERVICIOS': 'S', 'PUNTOVENTA': 'PV',
}
CATEGORY_SHEET_CODES = {
    'R': 'R', 'R_NW': 'R', 'R_CHEM': 'R', 'R_FAN': 'R', 'B': 'B', 'S': 'S',
}
PAYMENT_METHOD_LABELS = dict(CorteDeCajaAdjustment.PAYMENT_METHOD_CHOICES)

# Spanish month abbreviations, matching the real sheet's own tab naming
# (e.g. "22.Sep", "15.Ago") - built explicitly rather than via
# date.strftime('%b'), which depends on the server's system locale and
# would silently render English abbreviations (Jan/Aug/Dec) on a server
# that isn't configured with an es_MX locale.
SPANISH_MONTH_ABBR = [
    'Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic',
]

HEADER_FILL = PatternFill(start_color='DDDDDD', end_color='DDDDDD', fill_type='solid')
HEADER_FONT = Font(bold=True)
TOTAL_FONT = Font(bold=True)


def _month_bounds(year, month):
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def _folio_prefixes(invoice_ids):
    """No. FACTURA on the real sheet is a display prefix (e.g. 'F', 'B',
    'A' - one admConceptos row per tax series) plus the bare folio number -
    see erp_schema_reference. Reconstructed here from AdmConceptos rather
    than carried through calculate_corte_de_caja, since Corte de Caja's own
    report doesn't otherwise need the display prefix.
    """
    concepto_by_invoice = dict(
        AdmDocumentos.objects.filter(CIDDOCUMENTO__in=invoice_ids).values_list(
            'CIDDOCUMENTO', 'CIDCONCEPTODOCUMENTO',
        )
    )
    prefix_by_concepto = dict(
        AdmConceptos.objects.values_list('CIDCONCEPTODOCUMENTO', 'CPREFIJOCONCEPTO')
    )
    return {
        invoice_id: (prefix_by_concepto.get(concepto_id) or 'F').strip()
        for invoice_id, concepto_id in concepto_by_invoice.items()
    }


def _write_day_sheet(wb, day, rows, folio_prefixes):
    sheet_name = f'{day.day:02d}.{SPANISH_MONTH_ABBR[day.month - 1]}'
    ws = wb.create_sheet(sheet_name[:31])

    ws['A1'] = 'CORTE DE CAJA COBRANZA GENERAL'
    ws['A1'].font = Font(bold=True, size=12)
    ws['C2'] = day
    ws['C2'].number_format = 'dd/mm/yyyy'

    header_row = 4
    for col, title in enumerate(HEADERS, start=1):
        cell = ws.cell(row=header_row, column=col, value=title)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL

    zone_totals = {}
    r = header_row + 1
    for row in sorted(rows, key=lambda x: (x['zone'] or '', x['cliente'])):
        folio_display = f"{folio_prefixes.get(row['invoice_id'], 'F')} {int(row['folio'])}"
        ws.cell(row=r, column=1, value=None)  # CUENTA - not decoded, left blank
        ws.cell(row=r, column=2, value=row['cliente'])
        ws.cell(row=r, column=3, value=folio_display)
        ws.cell(row=r, column=4, value='A' if row['abono'] else None)
        ws.cell(row=r, column=5, value=float(row['amount']))
        ws.cell(row=r, column=6, value=None)  # ENTREGA - meaning never decoded
        ws.cell(row=r, column=7, value=None)  # RECIBE - meaning never decoded
        if row['due_date']:
            due_cell = ws.cell(row=r, column=8, value=row['due_date'].date())
            due_cell.number_format = 'dd/mm/yyyy'
        ws.cell(row=r, column=9, value=ZONE_SHEET_CODES.get(row['zone'], row['zone']))
        ws.cell(row=r, column=10, value=CATEGORY_SHEET_CODES.get(row['category'], row['category']))
        ws.cell(row=r, column=11, value=row['note'] or None)
        method_label = PAYMENT_METHOD_LABELS.get(row['payment_method'], '')
        if row['payment_method'] and not row['payment_method_confirmed']:
            method_label += ' (sugerido)'
        ws.cell(row=r, column=12, value=method_label or None)
        ws.cell(row=r, column=13, value=row['bank'] or None)

        if not row['excluded']:
            zone_totals[row['zone']] = zone_totals.get(row['zone'], 0) + float(row['amount'])
        r += 1

    r += 1
    # Sort by an explicit string key rather than the raw tuple - zone
    # should never actually be None given the upstream zone-scope filter,
    # but sorted() comparing None to a str raises, and this is a cheap
    # guard against that if that assumption ever breaks.
    for zone, total in sorted(zone_totals.items(), key=lambda kv: kv[0] or ''):
        ws.cell(row=r, column=2, value=f'TOTAL {ZONE_SHEET_CODES.get(zone, zone)}').font = TOTAL_FONT
        ws.cell(row=r, column=5, value=total).font = TOTAL_FONT
        r += 1
    ws.cell(row=r, column=2, value='TOTAL CORTE').font = TOTAL_FONT
    ws.cell(row=r, column=5, value=sum(zone_totals.values())).font = TOTAL_FONT

    widths = [14, 32, 12, 8, 12, 10, 10, 12, 10, 8, 28, 20, 24]
    for col, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.freeze_panes = f'A{header_row + 1}'


def build_month_workbook(year, month):
    month_start = date(year, month, 1)
    if month_start < EARLIEST_EXPORT_MONTH:
        earliest_label = SPANISH_MONTH_ABBR[EARLIEST_EXPORT_MONTH.month - 1]
        raise ValueError(
            f'No se generan reportes anteriores a {earliest_label} {EARLIEST_EXPORT_MONTH.year} - '
            'este reemplazo automático inicia desde ese mes, no reconstruye el histórico.'
        )

    date_from, date_to = _month_bounds(year, month)
    result = calculate_corte_de_caja(date_from, date_to)

    rows_by_day = {}
    for row in result['rows']:
        rows_by_day.setdefault(row['event_date'], []).append(row)

    invoice_ids = {row['invoice_id'] for row in result['rows']}
    folio_prefixes = _folio_prefixes(invoice_ids)

    wb = Workbook()
    wb.remove(wb.active)  # openpyxl creates a default blank sheet - unused, this workbook is all named day sheets
    for day in sorted(rows_by_day):
        _write_day_sheet(wb, day, rows_by_day[day], folio_prefixes)

    if not wb.sheetnames:
        # No payments at all this month (e.g. exporting the current month
        # before any data exists yet) - still produce a valid, openable
        # workbook rather than erroring, so the scheduled job never fails
        # just because a month is quiet so far.
        wb.create_sheet('Sin datos')

    return wb


def export_month(year, month, output_dir=None):
    """Writes (overwrites) the month's workbook to CORTE_DE_CAJA_EXPORT_DIR
    (or `output_dir`) - see core/settings.py. That directory is expected to
    be an SMB-shared folder on the office server so the accountant/manager
    can open the file directly, without any manual export step; making the
    directory actually SMB-visible is a one-time server/IT configuration,
    not something this function does.
    """
    output_dir = Path(output_dir or settings.CORTE_DE_CAJA_EXPORT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    wb = build_month_workbook(year, month)
    filename = f'Corte de Caja {year}-{month:02d}.xlsx'
    path = output_dir / filename

    # Write to a temp file then replace atomically, so a job that runs
    # while someone has the file open (or another export overlaps) never
    # leaves a half-written, corrupt workbook in the shared folder. If she
    # has the file open in Excel when this runs, Windows may refuse the
    # replace outright (a held file lock, not just a race) - that raises
    # here rather than corrupting anything; the temp file is simply
    # overwritten and retried on the next scheduled run.
    tmp_path = output_dir / f'.{filename}.tmp'
    wb.save(tmp_path)
    tmp_path.replace(path)
    return path
