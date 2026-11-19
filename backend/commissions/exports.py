"""Monthly Comisiones workbook in the shared Auto folder, next to Corte de Caja's.

Layout follows management's own "Relación de comisiones por cobranza" sheets (one per salesperson, asked
for 2026-11-07 with every zone): one sheet per zone with Fecha (paid date, on the first row of each day),
Nombre, Folio, Fecha Emisión, Fecha Vencimiento, Importe, % Comisión, Total, category and a note, then
TOTALES and the signature block. Differences agreed with the user: Importe is the pre-tax amount the
platform computes on (Total = Importe x %, no /1.16), column I is the platform's category, and a Resumen
sheet lists the zone totals. The numbers are exactly the Comisiones page's (calculate_commissions).
"""

from collections import defaultdict
from datetime import date
from pathlib import Path

from django.conf import settings
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from commissions.services import PUNTOVENTA_RATE_CODE, ZONE_SCOPE, calculate_commissions
from corte_de_caja.exports import ExportFileInUse, _month_bounds, _zone_labels, save_report

# September 2026 is the first month validated to the cent against management's sheets.
EARLIEST_EXPORT_MONTH = date(2026, 9, 1)
SPANISH_MONTHS = [
    'ENERO', 'FEBRERO', 'MARZO', 'ABRIL', 'MAYO', 'JUNIO', 'JULIO', 'AGOSTO', 'SEPTIEMBRE', 'OCTUBRE',
    'NOVIEMBRE', 'DICIEMBRE',
]
# Styles copied from management's sheet: no borders, Arial 8 rows under an Arial 9 title on a light gray band,
# white-on-gray headers over A-H only (I and J, category and note, have none), default column widths but Nombre.
HEADERS = ['Fecha', 'Nombre', 'Folio', 'Fecha Emisión', 'Fecha Vencimiento', 'Importe', '% Comisión', 'Total']
NAME_WIDTH = 40
DATE_FORMAT = 'd-mmm-yy'
PERCENT_FORMAT = '0.00%'
MONEY_FORMAT = '_-* #,##0.00_-;\\-* #,##0.00_-;_-* "-"??_-;_-@_-'
HEADER_ROW = 6
CENTERED_COLUMNS = (3, 4, 5, 6, 7, 9)

FONT = Font(name='Arial', size=8)
FONT_BOLD = Font(name='Arial', size=8, bold=True)
FONT_TITLE = Font(name='Arial', size=9, bold=True)
FONT_HEADER = Font(name='Arial', size=8, bold=True, color='FFFFFF')
TITLE_FILL = PatternFill('solid', fgColor='D9D9D9')
HEADER_FILL = PatternFill('solid', fgColor='808080')
TOTAL_BORDER = Border(bottom=Side(style='double'))
CENTER = Alignment(horizontal='center')


def _note(line):
    notes = []
    if line.get('manual'):
        notes.append('Monto manual')
    if line.get('excluded'):
        notes.append('Excluida')
    if line.get('rate_code') == PUNTOVENTA_RATE_CODE:
        notes.append('PV')
    if line.get('cash_share') is not None:
        notes.append(f"Pagada {line['cash_share']:.0%} en dinero")
    if line.get('rate_note'):
        notes.append(line['rate_note'])
    elif line.get('producto_nombre') and line.get('manual'):
        notes.append(line['producto_nombre'])
    return ' · '.join(notes)


def _naive(value):
    return value.replace(tzinfo=None) if value is not None else None


def _write_zone_sheet(wb, zone, label, lines, period):
    ws = wb.create_sheet(zone[:31])
    ws.sheet_format.baseColWidth = 10
    ws['A1'] = 'RELACION DE COMISIONES POR COBRANZA'
    for col in range(1, 10):
        ws.cell(1, col).fill = TITLE_FILL
    ws.merge_cells('A1:I1')
    ws['A1'].font, ws['A1'].alignment = FONT_TITLE, CENTER
    ws['B3'] = period
    ws['B4'] = label
    ws['B3'].font = ws['B4'].font = FONT_TITLE
    ws.row_dimensions[HEADER_ROW].height = 22.5
    for col, header in enumerate(HEADERS, 1):
        cell = ws.cell(HEADER_ROW, col, header)
        cell.font, cell.fill = FONT_HEADER, HEADER_FILL
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

    row = HEADER_ROW
    last_day = None
    for line in sorted(lines, key=lambda l: (l['paid_date'], l['cliente'] or '', l['folio_display'])):
        row += 1
        day = line['paid_date'].date() if line['paid_date'] else None
        manual = line.get('manual')
        amount = line['net_amount'] * (line['cash_share'] if line.get('cash_share') is not None else 1)
        rate = 0 if line.get('excluded') else line['rate']
        values = [
            day if day != last_day else None, line['cliente'], line['folio_display'],
            _naive(line.get('invoice_date')), _naive(line.get('due_date')),
            float(amount), None if manual else float(rate),
            float(line['commission']) if manual else f'=F{row}*G{row}',
            line.get('category') or '', _note(line),
        ]
        last_day = day
        for col, value in enumerate(values, 1):
            cell = ws.cell(row, col, value)
            cell.font = FONT_BOLD if col == 1 else FONT
            if col in CENTERED_COLUMNS:
                cell.alignment = CENTER
        for col in (1, 4, 5):
            ws.cell(row, col).number_format = DATE_FORMAT
        ws.cell(row, 6).number_format = ws.cell(row, 8).number_format = MONEY_FORMAT
        ws.cell(row, 7).number_format = PERCENT_FORMAT

    total_row = row + 2
    cell = ws.cell(total_row, 5, 'TOTALES')
    cell.font, cell.alignment = FONT_BOLD, CENTER
    for col, letter in ((6, 'F'), (8, 'H')):
        cell = ws.cell(total_row, col, f'=SUM({letter}{HEADER_ROW + 1}:{letter}{row})' if row > HEADER_ROW else 0)
        cell.font, cell.number_format, cell.alignment, cell.border = FONT_BOLD, MONEY_FORMAT, CENTER, TOTAL_BORDER

    for offset, left, right in ((3, 'REVISA Y AUTORIZA', 'RECIBE DE CONFORMIDAD'),
                                (7, settings.COMISIONES_REVIEWER, label)):
        ws.cell(total_row + offset, 1, left).font = FONT_BOLD
        cell = ws.cell(total_row + offset, 5, right)
        cell.font, cell.alignment = FONT_BOLD, CENTER

    ws.column_dimensions['B'].width = NAME_WIDTH
    ws.freeze_panes = f'A{HEADER_ROW + 1}'
    ws.print_title_rows = f'{HEADER_ROW}:{HEADER_ROW}'
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    return f"='{ws.title}'!H{total_row}"


def build_month_workbook(year, month):
    if date(year, month, 1) < EARLIEST_EXPORT_MONTH:
        raise ValueError(f'No se generan comisiones anteriores a {EARLIEST_EXPORT_MONTH:%Y-%m}.')
    date_from, date_to = _month_bounds(year, month)
    result = calculate_commissions(date_from, date_to)
    period = f'DEL 01 AL {date_to.day:02d} DE {SPANISH_MONTHS[month - 1]} DE {year}'

    lines_by_zone = defaultdict(list)
    for line in result['lines']:
        lines_by_zone[line['zone']].append(line)
    # Every in-scope zone gets a sheet, even an empty one; PUNTOVENTA's invoices belong to a route.
    zones = [z for z in ZONE_SCOPE if z != 'PUNTOVENTA'] + sorted(z for z in lines_by_zone if z not in ZONE_SCOPE)
    labels = _zone_labels()

    wb = Workbook()
    summary = wb.active
    summary.title = 'Resumen'
    summary['A1'] = 'RELACION DE COMISIONES POR COBRANZA'
    summary['A1'].fill = summary['B1'].fill = TITLE_FILL
    summary.merge_cells('A1:B1')
    summary['A1'].font, summary['A1'].alignment = FONT_TITLE, CENTER
    summary['A2'] = period
    summary['A2'].font = FONT_TITLE
    summary['A4'], summary['B4'] = 'Zona', 'Total'
    for cell in (summary['A4'], summary['B4']):
        cell.font, cell.fill, cell.alignment = FONT_HEADER, HEADER_FILL, CENTER
    row = 4
    for zone in zones:
        row += 1
        summary.cell(row, 1, labels.get(zone, zone)).font = FONT
        cell = summary.cell(row, 2, _write_zone_sheet(wb, zone, labels.get(zone, zone), lines_by_zone[zone], period))
        cell.font, cell.number_format = FONT, MONEY_FORMAT
    summary.cell(row + 1, 1, 'TOTAL').font = FONT_BOLD
    cell = summary.cell(row + 1, 2, f'=SUM(B5:B{row})')
    cell.font, cell.number_format, cell.border = FONT_BOLD, MONEY_FORMAT, TOTAL_BORDER

    pending = result['unresolved_payment_date']
    if pending['count']:
        # The month isn't closed while Contabilidad is missing pólizas: say so where it's read.
        summary.cell(row + 3, 1, (
            f"{pending['count']} factura(s) pagada(s) en Comercial por ${pending['total_amount']:,.2f} aún sin "
            'póliza en Contabilidad: no están incluidas.'
        )).font = FONT_BOLD
    summary.column_dimensions['A'].width = 40
    summary.column_dimensions['B'].width = 16
    return wb


def export_month(year, month, output_dir=None):
    output_dir = Path(output_dir or settings.COMISIONES_EXPORT_DIR) / str(year)
    output_dir.mkdir(parents=True, exist_ok=True)
    return save_report(build_month_workbook(year, month), output_dir, f'Comisiones {year}-{month:02d}.xlsx')


def export_recent_months(today=None):
    """This month and last month (last month keeps changing while late pólizas are posted), like Corte."""
    today = today or date.today()
    last_month = date(today.year - (today.month == 1), 12 if today.month == 1 else today.month - 1, 1)
    results = []
    for month_start in (last_month, today.replace(day=1)):
        if month_start < EARLIEST_EXPORT_MONTH:
            continue
        label = f'{month_start:%Y-%m}'
        try:
            results.append({'month': label, 'path': str(export_month(month_start.year, month_start.month))})
        except ExportFileInUse:
            results.append({'month': label, 'error': 'El archivo está abierto en Excel; se actualizará cuando lo cierren.'})
    return results
