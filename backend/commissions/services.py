"""Per-line-item commission calculation.

This is a real, payroll-affecting calculation built from rules confirmed with
management across several rounds of clarification (see the sales-commissions
project memory) - don't change rates, decay, category classification, or the
payment-date derivation below without re-confirming.

Every ERP access in this module is a read (.filter()/.values()) against the
'erp' connection. Nothing here ever writes to the ERP - all app-owned state
(rates, the zero-commission list) lives in the local commissions models.
"""

import re
import unicodedata
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone as dt_timezone
from decimal import Decimal

from django.db import connections

from api.models import AdmAgentes, AdmClasificacionesValores, AdmConceptos, AdmDocumentos, AdmMovimientos, AdmProductos

from .models import CommissionCategoryRate, InvoiceCommissionOverride, PuntoVentaClientZone, ZeroCommissionProduct

FACTURA_DOC_TYPE = 4
DEVOLUCION_DOC_TYPE = 5  # Devolucion sobre Venta - a return against a Factura, not a real sale.
NOTA_CREDITO_DOC_TYPE = 7
PAGO_DOC_TYPES = (9, 10, 12)
PAGO_CLIENTE_DOC_TYPE = 9  # "Pago del cliente" - the only one of PAGO_DOC_TYPES ever applied to a 2026 Factura

# The Comercial database (adAGROPECUARIA_2018, everything above) is only half
# of this Contpaqi install - there's a separate accounting-module database
# with the true, itemized payment-application ledger. Found 2026-09-17 after
# the user manually traced three payments in Contpaqi that the Comercial-side
# CREFERENCIA text alone couldn't resolve (blank, or a bulk payment whose
# reference didn't list every invoice it covered). Every sale/payment is
# mirrored there as an accounting entry with a clean, unambiguous folio
# reference - even bulk payments get one itemized line per invoice. Verified
# against real data: raised the September resolution rate from 84% to 96%.
LEDGER_DATABASE = 'ctAGROPECUARIA_SANTA_MARIA_SA_DE_CV'
LEDGER_PAGO_CONCEPTO = 'PAGO DEL CLIENTE'
LEDGER_INGRESOS_TIPOPOL = 1  # TiposPolizas.Id 1 = "Ingresos"

BIONAT_SUPPLIER_NAME = 'BIONAT-SANO, SA DE CV'
# Rate exceptions confirmed by management 2026-09-19, while reconciling
# against their real commission tracking (see project memory for the full
# investigation) - all are Refacciones by product type but start at 4%,
# not R's usual 6%. None of these fully explain that reconciliation's
# larger, still-open rate gap on their own; each closes a real slice of it.
#
# Mats/matting hardware: two genuinely different product families both
# read as "mats" - the North West Rubber supplier's own line (CCODIGOPRODUCTO
# like 3000xxx), AND a second family under the 4999-1115- code prefix
# (mats, installation strips, and the mat-fixing bolts/nails, e.g.
# "CLAVO ESPECIAL 212 2½\" (PERNO DE EXPANSION)") whose supplier is
# recorded as GEA FARM TECHNOLOGIES or PROVEEDORES VARIOS, NOT North West
# Rubber - checking supplier alone missed 14 of these 19 products. The user
# explicitly asked for the bolts to be grouped with the mats, so both
# families share one rate code.
NORTHWEST_RUBBER_SUPPLIER_NAME = 'NORTH WEST RUBBER'
NORTHWEST_RUBBER_CODE_PREFIX = '4999-1115-'
# Chemicals (LUXSAN, LUXTEK, OXYCIDE, TRI-PFAN, LAC ACIDO, THERATRATE, ...):
# span multiple suppliers (mostly GEA FARM TECHNOLOGIES, same as ordinary
# spare parts) so supplier can't detect them - classification slot 2 (a
# finer product-line field) cleanly does, with no other chemical-sounding
# values found in that slot's full taxonomy.
CHEMICAL_CLASSIFICATIONS = {'DETERGENTES NACIONALES', 'DETERGENTES SURGE'}
# Fans: span multiple suppliers AND multiple classification-2 values, so
# neither field detects them - the product name is the only consistent
# signal.
FAN_NAME_MARKER = 'VENTILADOR'
SERVICE_PRODUCT_TYPE = 3

# Zones in scope for v1 (confirmed by management, 2026-09-15): BIONAT and
# ZONA3 no longer have active salespeople and SUPERVISOR is a shared/generic
# login - all three, plus the unassigned agent, are omitted entirely unless a
# future feature needs historical/past-years reporting.
ZONE_SCOPE = {
    'ZONA1': 1,
    'ZONA2': 2,
    'OFICINA': 4,
    'SERVICIOS': 5,
    'PUNTOVENTA': 9,
}
# PUNTOVENTA is only a real, standalone commission-earning zone in
# ZONE_SCOPE above for querying purposes (its Facturas still need to be
# fetched) - per management, every one of its invoices actually belongs to
# a ZONA1/ZONA2 salesperson (see PuntoVentaClientZone) at this flat rate,
# never PUNTOVENTA itself.
PUNTOVENTA_ZONE_NAME = 'PUNTOVENTA'
PUNTOVENTA_RATE_CODE = 'PUNTOVENTA'

# How far before date_from to look for still-open invoices that might get
# paid off (and therefore become commission-eligible) within the requested
# period. Was 120 days until 2026-09-28, which silently dropped real
# commissions: an invoice on long credit terms paid late still earns (decay
# only reaches zero 12 weeks past the DUE date), but if it was invoiced more
# than 120 days before the queried month it never appeared in any month at
# all - not in the totals, not in the manual-review bucket. Found on folio
# 19892 (invoiced Mar 20 on 90-day terms, paid Aug 13 - 54 days late, still
# 2%); 16 invoices ($153k of sales) paid in 2026 were affected. Resolution is
# window-independent (see fetch_payment_docs), so a wider floor only costs
# query size.
DEFAULT_LOOKBACK_DAYS = 365

# Ledger lines naming this generic public-sales account can't be tied to one
# specific invoice by client name alone.
GENERIC_CLIENT_PREFIX = 'VENTAS PUBLIC'

FOLIO_TOKEN_RE = re.compile(r'(\d{3,7})')
# Rare (3 of 36,799 payment references dataset-wide) but real: a compressed
# shorthand like "4395-96" meaning folios 4395 AND 4396 - the second number
# is just the abbreviated trailing digits of the first, not a separate
# 2-digit folio. Caught 2026-09-17 after the user found a real payment
# (folio 19401, WN EL NOGAL) referencing "4395-96" whose second folio
# (4396, a $174k invoice) FOLIO_TOKEN_RE alone silently missed - it never
# matches 1-2 digit runs on their own.
FOLIO_RANGE_SHORTHAND_RE = re.compile(r'(\d{3,7})-(\d{1,2})(?!\d)')


def _extract_folio_tokens(text):
    tokens = set(FOLIO_TOKEN_RE.findall(text))
    for first, suffix in FOLIO_RANGE_SHORTHAND_RE.findall(text):
        tokens.add(first[:-len(suffix)] + suffix)
    return tokens


class CommissionRepository:
    @staticmethod
    def fetch_scoped_facturas(floor_date, date_to):
        """Real, zone-scoped, non-cancelled Facturas dated within
        [floor_date, date_to], paid or not. Commissions keeps only the
        CPENDIENTE=0 ones for its totals, but the ledger attribution (see
        attribute_ledger_payments) needs the unpaid ones too: to know which
        series+folio pairs are shared, and as repair targets.
        """
        return list(
            AdmDocumentos.objects.filter(
                CIDDOCUMENTODE=FACTURA_DOC_TYPE,
                CCANCELADO=0,
                CIDAGENTE__in=ZONE_SCOPE.values(),
                CFECHA__date__gte=floor_date,
                CFECHA__date__lte=date_to,
            ).values(
                'CIDDOCUMENTO', 'CFOLIO', 'CFECHA', 'CFECHAVENCIMIENTO', 'CTOTAL', 'CPENDIENTE',
                'CIDCLIENTEPROVEEDOR', 'CRAZONSOCIAL', 'CIDAGENTE', 'CIDCONCEPTODOCUMENTO',
            )
        )

    @staticmethod
    def fetch_facturas_for_corte(date_from, date_to, candidate_lookback_days):
        """Candidate real Facturas for the Corte de Caja report (see
        corte_de_caja app) - a DAILY CASH-COLLECTIONS log, not an aging
        report (see that app's services.py docstring for the full
        correction - an earlier version of this method served a design that
        turned out not to match the real spreadsheet at all).

        Corte de Caja needs every Factura that could plausibly have had a
        payment EVENT land in [date_from, date_to] - which, since a large
        sale can take months to fully settle via several installments (see
        commissions' own CIDDOCUMENTO 100223 case, a ~6-month spread), means
        casting back further than the report window itself. Returns real,
        zone-scoped, non-cancelled Facturas dated within
        [date_from - candidate_lookback_days, date_to] regardless of
        CPENDIENTE - unlike commissions' paid-only set, being currently unpaid
        doesn't disqualify a Factura here, since we're matching against
        historical ledger/payment events dated in the window, not today's
        live balance.
        """
        floor_date = date_from - timedelta(days=candidate_lookback_days)
        return CommissionRepository.fetch_scoped_facturas(floor_date, date_to)

    @staticmethod
    def fetch_payment_docs(floor_date):
        # Only corte_de_caja reads these now (commissions dates come from the
        # ledger alone since 2026-09-28). Searched from the invoice lookback
        # floor through TODAY - never capped at the report's date_to. Capping
        # it there was a real bug when commissions still used this: for an
        # invoice settled via several installments in different months, the
        # old Comercial-side resolver took the latest payment found
        # *within the queried window*, so querying December only saw the
        # December installment (resolved paid_date = December), querying
        # January then saw December+January (resolved paid_date = January),
        # and querying February saw all three - the same invoice's full
        # commission got recomputed and counted again in EVERY month that
        # contained a referencing payment. Searching through today instead
        # of date_to means the resolved paid_date is the true, final one
        # and doesn't change depending on which month is being viewed - an
        # invoice can only ever land in exactly one month's totals. Found
        # 2026-09-15 from a report showing the same invoice generating
        # commission in three different months.
        return list(
            AdmDocumentos.objects.filter(
                CIDDOCUMENTODE__in=PAGO_DOC_TYPES,
                CFECHA__date__gte=floor_date,
                CFECHA__date__lte=date.today(),
            ).exclude(CREFERENCIA__isnull=True).exclude(CREFERENCIA='').values(
                'CFECHA', 'CIDCLIENTEPROVEEDOR', 'CREFERENCIA', 'CTOTAL',
            )
        )

    @staticmethod
    def fetch_settlements(floor_date):
        """How Contpaqi Comercial settled each Factura dated since floor_date,
        from its exact payment-to-invoice record (admAsocCargosAbonos, see
        fetch_comercial_applications): {invoice_id: {'cash': applied by
        customer payments, 'credit': applied by credit notes and returns}}.
        """
        with connections['erp'].cursor() as cursor:
            cursor.execute(
                """
                SELECT a.CIDDOCUMENTOCARGO, ab.CIDDOCUMENTODE, SUM(a.CIMPORTEABONO)
                FROM admAsocCargosAbonos a
                JOIN admDocumentos ab ON ab.CIDDOCUMENTO = a.CIDDOCUMENTOABONO
                JOIN admDocumentos ca ON ca.CIDDOCUMENTO = a.CIDDOCUMENTOCARGO
                WHERE ca.CIDDOCUMENTODE = %s AND ca.CFECHA >= %s
                  AND ab.CIDDOCUMENTODE IN (%s, %s, %s)
                GROUP BY a.CIDDOCUMENTOCARGO, ab.CIDDOCUMENTODE
                """,
                [FACTURA_DOC_TYPE, floor_date, PAGO_CLIENTE_DOC_TYPE, NOTA_CREDITO_DOC_TYPE, DEVOLUCION_DOC_TYPE],
            )
            settlements = defaultdict(lambda: {'cash': 0.0, 'credit': 0.0})
            for invoice_id, doc_type, amount in cursor.fetchall():
                settlements[invoice_id]['cash' if doc_type == PAGO_CLIENTE_DOC_TYPE else 'credit'] += amount or 0
            return settlements

    @staticmethod
    def fetch_concepto_series():
        # blank/null CSERIEPOROMISION means the 16%-taxed default series -
        # normalized to 'F' to match how it's written in the ledger's own
        # Referencia text (e.g. 'F-20512' vs 'B 19778').
        return {
            cid: (serie or 'F')
            for cid, serie in AdmConceptos.objects.values_list('CIDCONCEPTODOCUMENTO', 'CSERIEPOROMISION')
        }

    @staticmethod
    def fetch_ledger_payment_lines(floor_date):
        """Raw cross-database read against the Contabilidad ledger (see
        LEDGER_DATABASE above) - still read-only, just not expressible
        through the Django ORM since it's a second database on the same SQL
        Server rather than a model in this app.

        Every MovimientosPoliza line for payment polizas in the window
        (PAGO DEL CLIENTE, plus any other Ingresos poliza - a few dozen a
        year are typed with the client's name as their concept instead, e.g.
        F 20933's Aug 6 and Aug 31 payments, and would otherwise be missed).
        Blank-Referencia lines are kept: those are the OTHER side of the same
        journal entry, the one that debits the real bank account the money
        landed in (only corte_de_caja reads them - attribute_ledger_payments
        skips them). Checked live 2026-09-24: every real
        payment debits one of a handful of actual bank accounts (see
        fetch_bank_accounts) - the business's Caja Chica (cash) account is
        used once in all of 2026, so this identifies WHICH BANK, not
        cash/terminal/cheque/transfer as such.
        """
        with connections['erp'].cursor() as cursor:
            cursor.execute(
                f"""
                SELECT mp.IdPoliza, LTRIM(RTRIM(mp.Referencia)), mp.Fecha, mp.Concepto,
                       mp.Importe, mp.TipoMovto, mp.IdCuenta
                FROM {LEDGER_DATABASE}.dbo.MovimientosPoliza mp
                JOIN {LEDGER_DATABASE}.dbo.Polizas p ON p.Id = mp.IdPoliza
                WHERE (p.Concepto = %s OR p.TipoPol = %s) AND mp.Fecha >= %s AND mp.Fecha <= %s
                """,
                [LEDGER_PAGO_CONCEPTO, LEDGER_INGRESOS_TIPOPOL, floor_date, date.today()],
            )
            return cursor.fetchall()

    @staticmethod
    def fetch_comercial_applications(floor_date):
        """Contpaqi Comercial's own record of which customer payment was
        applied to which invoice, and for how much (admAsocCargosAbonos) -
        exact, unlike the free-text CREFERENCIA: checked 2026-09-28, the
        applied amounts add up to CTOTAL - CPENDIENTE on every one of the
        3,687 non-cancelled 2026 invoices, and a payment covering several
        invoices is split per invoice. Only customer payments (Pago del
        cliente); credit notes and returns are applied here too but aren't
        cash. Rows: (invoice_id, payment_id, payment_date, applied_date,
        amount, payment_series, payment_folio).
        """
        with connections['erp'].cursor() as cursor:
            cursor.execute(
                """
                SELECT a.CIDDOCUMENTOCARGO, a.CIDDOCUMENTOABONO, ab.CFECHA, a.CFECHAABONOCARGO,
                       a.CIMPORTEABONO, LTRIM(RTRIM(ab.CSERIEDOCUMENTO)), ab.CFOLIO
                FROM admAsocCargosAbonos a
                JOIN admDocumentos ab ON ab.CIDDOCUMENTO = a.CIDDOCUMENTOABONO
                WHERE ab.CIDDOCUMENTODE = %s AND ab.CCANCELADO = 0 AND ab.CFECHA >= %s
                """,
                [PAGO_CLIENTE_DOC_TYPE, floor_date],
            )
            return cursor.fetchall()

    @staticmethod
    def fetch_poliza_labels(poliza_ids):
        """{poliza id: 'Ingresos 235'} - the type and folio the accountant
        searches by in Contpaqi Contabilidad."""
        labels = {}
        ids = sorted(poliza_ids)
        with connections['erp'].cursor() as cursor:
            for start in range(0, len(ids), 1000):  # SQL Server caps a query at 2,100 parameters
                chunk = ids[start:start + 1000]
                cursor.execute(
                    f"""
                    SELECT p.Id, t.Nombre, p.Folio
                    FROM {LEDGER_DATABASE}.dbo.Polizas p
                    JOIN {LEDGER_DATABASE}.dbo.TiposPolizas t ON t.Id = p.TipoPol
                    WHERE p.Id IN ({', '.join(['%s'] * len(chunk))})
                    """,
                    chunk,
                )
                labels.update({id_: f'{tipo} {folio}' for id_, tipo, folio in cursor.fetchall()})
        return labels

    @staticmethod
    def fetch_client_account_codes():
        """Contabilidad's per-client accounts (chart-of-accounts prefix '103',
        "Clientes") keyed by id - the accountant's sheet has a CUENTA column
        holding exactly this code (e.g. 103-107-408) for each client.
        """
        with connections['erp'].cursor() as cursor:
            cursor.execute(f"SELECT Id, Codigo FROM {LEDGER_DATABASE}.dbo.Cuentas WHERE Codigo LIKE '103%'")
            return {id_: (codigo or '').strip() for id_, codigo in cursor.fetchall()}

    @staticmethod
    def fetch_bank_accounts():
        """Real bank/cash accounts (Cuentas.Codigo under the 'Circulante'
        chart-of-accounts group, prefix '1001') - used to label which
        account a ledger payment's bank-debit line (see
        fetch_ledger_payment_lines) landed in.
        """
        with connections['erp'].cursor() as cursor:
            cursor.execute(f"SELECT Id, Codigo, Nombre FROM {LEDGER_DATABASE}.dbo.Cuentas WHERE Codigo LIKE '1001%'")
            return {id_: (codigo, nombre) for id_, codigo, nombre in cursor.fetchall()}

    @staticmethod
    def fetch_movimientos(invoice_ids):
        if not invoice_ids:
            return []
        return list(
            AdmMovimientos.objects.filter(
                CIDDOCUMENTO__in=invoice_ids,
                CIDDOCUMENTODE=FACTURA_DOC_TYPE,
            ).values(
                'CIDDOCUMENTO', 'CIDPRODUCTO', 'CNETO', 'CUNIDADES',
                'CDESCUENTO1', 'CDESCUENTO2', 'CDESCUENTO3', 'CDESCUENTO4', 'CDESCUENTO5',
            )
        )

    @staticmethod
    def fetch_productos(product_ids):
        if not product_ids:
            return []
        return list(
            AdmProductos.objects.filter(CIDPRODUCTO__in=product_ids).values(
                'CIDPRODUCTO', 'CCODIGOPRODUCTO', 'CNOMBREPRODUCTO', 'CTIPOPRODUCTO',
                'CIDVALORCLASIFICACION1', 'CIDVALORCLASIFICACION2',
            )
        )

    @staticmethod
    def fetch_brand_names():
        return dict(AdmClasificacionesValores.objects.values_list('CIDVALORCLASIFICACION', 'CVALORCLASIFICACION'))

    @staticmethod
    def fetch_agent_codes():
        return dict(AdmAgentes.objects.values_list('CIDAGENTE', 'CCODIGOAGENTE'))

    @staticmethod
    def fetch_puntoventa_client_zones():
        return dict(
            PuntoVentaClientZone.objects.filter(active=True).values_list('cliente_id', 'zone')
        )

    @staticmethod
    def search_facturas(folio):
        """Used by the management-only invoice-search endpoint (the "Add"
        override picker) - real Facturas matching a folio number, not
        restricted to any zone scope or date window since management may be
        looking for something outside the normal report (per the EQ/COWSCOUT
        gap documented in the project memory). Cancelled invoices excluded.
        """
        return list(
            AdmDocumentos.objects.filter(
                CIDDOCUMENTODE=FACTURA_DOC_TYPE,
                CCANCELADO=0,
                CFOLIO=folio,
            ).values(
                'CIDDOCUMENTO', 'CFOLIO', 'CFECHA', 'CIDCLIENTEPROVEEDOR', 'CRAZONSOCIAL', 'CIDAGENTE', 'CTOTAL',
            )[:20]
        )

    @staticmethod
    def fetch_overrides():
        return {o.invoice_id: o for o in InvoiceCommissionOverride.objects.all()}


def _normalize_name(value):
    if not value:
        return ''
    stripped = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    return stripped.upper().strip()


# How close the cumulative amount applied against a Factura's ledger
# reference needs to get to its CTOTAL before a date is trusted as the true
# full-payment date. Generous enough to absorb the few-cents rounding seen
# in real netted entries (e.g. an "$800,000" installment posting as
# 799,999.98), nowhere near loose enough to accept a partial installment.
LEDGER_FULL_PAYMENT_TOLERANCE = 1.0


def attribute_ledger_payments(facturas, ledger_lines, concepto_series):
    """PRIMARY payment source (2026-09-17): the Contpaqi Contabilidad ledger
    (see LEDGER_DATABASE) mirrors every sale/payment as an accounting entry
    with a clean folio reference - even bulk payments covering several
    invoices get one itemized line per invoice there, unlike the Comercial
    side's free-text CREFERENCIA which is sometimes blank and sometimes lists
    only some of the invoices a bulk payment actually covers. Verified
    against three real cases the user found by hand in Contpaqi, and raised
    September's resolution rate from 84% to 96%.

    Shared by commissions (the date an invoice reached full payment, see
    _paid_dates_from_ledger) and corte_de_caja (every dated installment).
    It used to be two copies; the corte one got five real bug fixes during
    the 2026-09-25/28 accuracy work and the commissions one got none, so
    there is now one implementation (audit 2026-09-28).

    The ledger's Referencia is built as "{serie}-{folio}" or "{serie} {folio}"
    (both forms seen in real data, inconsistently) where serie is the tax
    series (A/B/F) - NOT the display prefix, which is always "F" regardless
    of series (see AdmConceptos.CSERIEPOROMISION vs CPREFIJOCONCEPTO). Lines
    are netted signed by TipoMovto (True adds, False subtracts - verified
    against real data, e.g. three lines netting to exactly a $500,000
    installment also visible on the Comercial side).

    `facturas` must be every candidate invoice, paid or not (see
    CommissionRepository.fetch_scoped_facturas) and needs CPENDIENTE.

    Returns {invoice_id: {event_date: [(id_poliza, signed_amount), ...]}}.
    """
    by_reference = defaultdict(list)
    for id_poliza, referencia, fecha, concepto, importe, tipo_movto, id_cuenta in ledger_lines:
        if not referencia:
            continue
        signed_amount = importe if tipo_movto else -importe
        by_reference[referencia.upper()].append((fecha.date(), _normalize_name(concepto), signed_amount, id_poliza))

    # Series+folio pairs shared by more than one candidate Factura - only
    # those need the client-name check to tell them apart. Enforcing it on
    # unique pairs silently dropped real payments whenever the ledger spelled
    # the client differently (truncated, typo'd, or the actual buyer on a
    # "Ventas Publico en General" invoice): found 2026-09-25 on F 20933,
    # where a 9,000 payment was reported as 1,241.38.
    reference_counts = defaultdict(int)
    for f in facturas:
        reference_counts[(concepto_series.get(f['CIDCONCEPTODOCUMENTO'], 'F'), int(f['CFOLIO']))] += 1

    # PASS 1 - per invoice, which ledger payments (by poliza, per day) it
    # accepts, plus "misfits": payments cited against an invoice they don't
    # fit (would push it past its own total, or carry another client's name).
    accepted = {}
    misfits = []
    for f in facturas:
        serie = concepto_series.get(f['CIDCONCEPTODOCUMENTO'], 'F')
        folio = int(f['CFOLIO'])
        client_name = _normalize_name(f['CRAZONSOCIAL'])
        total = f['CTOTAL'] or 0
        ambiguous = reference_counts[(serie, folio)] > 1

        lines_by_date = defaultdict(list)
        for referencia in (f'{serie}-{folio}'.upper(), f'{serie} {folio}'.upper()):
            for event_date, ledger_client_name, signed_amount, id_poliza in by_reference.get(referencia, []):
                name_ok = not client_name or client_name in ledger_client_name
                if ambiguous and not name_ok:
                    continue
                lines_by_date[event_date].append((id_poliza, signed_amount, name_ok, ledger_client_name))
        if not lines_by_date:
            continue

        by_date = {}
        cumulative = 0.0
        for event_date in sorted(lines_by_date):
            lines = lines_by_date[event_date]
            names = {p: name for p, _, _, name in lines}
            # A poliza where at least one line names the client is trusted
            # outright (the ledger often truncates or misspells the name on
            # its other lines). A poliza where NO line names the client - on
            # a unique series+folio - is either the real buyer on a "Ventas
            # Publico en General" invoice or a mistyped folio pointing at
            # the wrong invoice; only attribute it if it still fits within
            # the invoice's total, otherwise it's a misfit for pass 2.
            named_polizas = {p for p, _, ok, _ in lines if ok}
            entries = [(p, a) for p, a, _, _ in lines if p in named_polizas]
            unnamed = defaultdict(float)
            for p, a, _, _ in lines:
                if p not in named_polizas:
                    unnamed[p] += a
            running = cumulative + sum(a for _, a in entries)
            for p, net in unnamed.items():
                if net > 0 and running + net <= total + LEDGER_FULL_PAYMENT_TOLERANCE:
                    entries.append((p, net))
                    running += net
                elif net > 0:
                    misfits.append({'invoice_id': f['CIDDOCUMENTO'], 'date': event_date, 'poliza': p,
                                    'amount': net, 'name': names[p], 'tentative': False})
            if not entries:
                continue
            # The ledger sometimes holds the same payment twice (found
            # 2026-09-25: two identical Polizas for one 35,060 payment, which
            # Contpaqi Comercial records once). Only when a day's entries
            # would push the invoice past its own total AND several are the
            # exact same amount, drop the extra copies - a lone overpayment
            # (e.g. 1,830 received on a 1,744.01 invoice) is real cash and
            # must stay as recorded.
            if total and len(entries) > 1 and len({amt for _, amt in entries}) == 1 and entries[0][1] > 0:
                while len(entries) > 1 and cumulative + sum(a for _, a in entries) > total + LEDGER_FULL_PAYMENT_TOLERANCE:
                    entries = entries[:-1]
            # Trusted polizas that still overshoot the total stay attributed
            # here unless pass 2 finds their real invoice (tentative misfits).
            net_by_poliza = defaultdict(float)
            for p, a in entries:
                net_by_poliza[p] += a
            run = cumulative
            for p, net in net_by_poliza.items():
                run += net
                if net > 0 and total and run > total + LEDGER_FULL_PAYMENT_TOLERANCE:
                    misfits.append({'invoice_id': f['CIDDOCUMENTO'], 'date': event_date, 'poliza': p,
                                    'amount': net, 'name': names.get(p, ''), 'tentative': True})
            by_date[event_date] = entries
            cumulative += sum(a for _, a in entries)
        if by_date:
            accepted[f['CIDDOCUMENTO']] = by_date

    # PASS 2 - a misfit payment usually means the ledger cites the wrong
    # invoice number (found 2026-09-25: 33,194 cited against a 10,290
    # invoice, when the paid one was the neighbouring folio). Move it only
    # when the evidence is unambiguous: another invoice whose client the
    # ledger line names, dated on/before the payment, that Comercial marks as
    # paid by exactly this much more than the ledger has attributed to it -
    # and exactly one such invoice. "Ventas Publico en General" is skipped as
    # a key: any number of unrelated invoices share it.
    def attributed_total(invoice_id):
        return sum(a for entries in accepted.get(invoice_id, {}).values() for _, a in entries)

    for m in misfits:
        candidates = []
        for u in facturas:
            uid = u['CIDDOCUMENTO']
            key = _normalize_name(u['CRAZONSOCIAL'])[:12]
            if uid == m['invoice_id'] or len(key) < 6 or key.startswith(GENERIC_CLIENT_PREFIX) or key not in m['name']:
                continue
            if u['CFECHA'].date() > m['date']:
                continue
            shortfall = (u['CTOTAL'] or 0) - (u['CPENDIENTE'] or 0) - attributed_total(uid)
            if abs(shortfall - m['amount']) <= LEDGER_FULL_PAYMENT_TOLERANCE:
                candidates.append(uid)
        if len(candidates) != 1:
            # No unambiguous home found: the cash was still received, so
            # keep it on the invoice the ledger cites (visible as an
            # over-total mismatch) rather than dropping it.
            if not m['tentative']:
                accepted.setdefault(m['invoice_id'], {}).setdefault(m['date'], []).append((m['poliza'], m['amount']))
            continue
        if m['tentative']:
            day = accepted[m['invoice_id']][m['date']]
            kept = [(p, a) for p, a in day if p != m['poliza']]
            if kept:
                accepted[m['invoice_id']][m['date']] = kept
            else:
                del accepted[m['invoice_id']][m['date']]
        accepted.setdefault(candidates[0], {}).setdefault(m['date'], []).append((m['poliza'], m['amount']))

    return accepted


def _paid_dates_from_ledger(facturas, accepted, cash_due=None):
    """The date each Factura reached full payment according to the ledger
    attribution above. Returns {invoice_id: paid_datetime}.

    `cash_due` ({invoice_id: amount}) is how much of each invoice was
    settled with money rather than credit notes/returns (see
    calculate_commissions); an invoice without an entry must be paid in full.

    CRITICAL - installments and full-payment verification: a large invoice
    can be settled via several dated entries under the same reference. Just
    taking the LATEST one is the mistake the old Comercial fallback made: found 2026-09-17 on a real $5,300,000 ZONA2 invoice (CIDDOCUMENTO
    100223) where the matching entries - Dec 30 $500k, Jan 30 $1M, Feb 27
    $500k, Jun 30 $799,999.98 - only sum to ~$2.8M, nowhere near the full
    $5.3M (this client has a running-account arrangement with a persistent
    unexplained balance gap). So entries are walked chronologically as a
    running total, and only the FIRST date where it reaches the Factura's
    own CTOTAL (within LEDGER_FULL_PAYMENT_TOLERANCE) is accepted. If it
    never does, the invoice is left unresolved here (not resolved to a
    wrong, too-early date) and goes to manual review.
    """
    paid_dates = {}
    for f in facturas:
        by_date = accepted.get(f['CIDDOCUMENTO'])
        if not by_date:
            continue
        total = (cash_due or {}).get(f['CIDDOCUMENTO'], f['CTOTAL'] or 0)
        cumulative = 0.0
        for event_date in sorted(by_date):
            cumulative += sum(a for _, a in by_date[event_date])
            if cumulative >= total - LEDGER_FULL_PAYMENT_TOLERANCE:
                paid_dates[f['CIDDOCUMENTO']] = datetime.combine(event_date, time(), tzinfo=dt_timezone.utc)
                break
    return paid_dates


def _classify_line(producto, brand_names, zero_codes):
    if producto['CCODIGOPRODUCTO'] in zero_codes:
        return 'ZERO'
    if brand_names.get(producto['CIDVALORCLASIFICACION1']) == BIONAT_SUPPLIER_NAME:
        return 'B'
    if producto['CTIPOPRODUCTO'] == SERVICE_PRODUCT_TYPE:
        return 'S'
    if brand_names.get(producto['CIDVALORCLASIFICACION1']) == NORTHWEST_RUBBER_SUPPLIER_NAME or \
            producto['CCODIGOPRODUCTO'].startswith(NORTHWEST_RUBBER_CODE_PREFIX):
        return 'R_NW'
    if brand_names.get(producto['CIDVALORCLASIFICACION2']) in CHEMICAL_CLASSIFICATIONS:
        return 'R_CHEM'
    if FAN_NAME_MARKER in (producto['CNOMBREPRODUCTO'] or '').upper():
        return 'R_FAN'
    # Default/fallback: covers R itself, EQ (no automatic detection rule
    # exists yet - deferred by management until there's a draft to look at),
    # and the rare tail codes management said not to worry about.
    return 'R'


def _rate_code_for(category, zone_code):
    if category == 'ZERO':
        return None
    if category == 'S':
        # Service items structurally only ever come from a route salesperson
        # or the maintenance crew (confirmed: OFICINA/PUNTOVENTA can't
        # produce one - nobody from those zones is ever on-site at a farm).
        return 'S_SALESPERSON' if zone_code in ('ZONA1', 'ZONA2') else 'S_SERVICIOS'
    return category


def _effective_rate(rate_row, days_late):
    """Decay is a weekly cutoff, not a continuous slope: being even 1 day
    late already costs one full decay step, the next step only lands once
    another 7 days pass (day 8), and so on - so weeks_completed is a
    ceiling, not days_late / 7. Confirmed by management, 2026-09-15.
    """
    if rate_row is None:
        return Decimal('0')
    if days_late <= 0:
        return rate_row.base_rate
    weeks_completed = -(-days_late // 7)  # ceiling division for positive ints
    decayed = rate_row.base_rate - (rate_row.decay_rate_per_week * weeks_completed)
    return max(decayed, Decimal('0'))


def _manual_line(base, override):
    """Synthetic single line representing a management manual-amount
    override, replacing whatever the automatic calculation produced (or,
    for an invoice outside the normally-computed set, standing in for it
    entirely). `base` supplies invoice_id/folio/cliente/paid_date/due_date/
    days_late - either a real computed line or the minimal dict built for
    an invoice found only via the search endpoint.
    """
    return {
        'invoice_id': base['invoice_id'],
        'folio': base['folio'],
        'client_id': base.get('client_id'),
        'cliente': base['cliente'],
        'zone': override.zone or base['zone'],
        'producto_codigo': None,
        'producto_nombre': override.note or 'Monto manual',
        'category': None,
        'rate_code': None,
        'quantity': None,
        'unit_amount': None,
        'net_amount': override.override_amount,
        'rate': None,
        'days_late': base.get('days_late', 0),
        'paid_date': base.get('paid_date'),
        'due_date': base.get('due_date'),
        'commission': override.override_amount,
        'manual': True,
    }


def _apply_overrides(lines, zone_totals, overrides):
    """Applies management's manual corrections (see InvoiceCommissionOverride)
    on top of the automatically-computed lines/zone_totals. Two independent
    modes per invoice: excluded (zero it out, keep visible) or
    override_amount (replace its commission with a flat manual figure).
    Invoices found only via the search endpoint (not naturally present in
    `lines` at all) are added as a single synthetic line, using the zone
    recorded on the override itself - the API layer requires that zone be
    set whenever override_amount is used, so this should always resolve.
    """
    lines_by_invoice = defaultdict(list)
    for line in lines:
        lines_by_invoice[line['invoice_id']].append(line)

    result_lines = []
    for invoice_id, invoice_lines in lines_by_invoice.items():
        override = overrides.get(invoice_id)
        if override is None:
            result_lines.extend(invoice_lines)
            continue

        zone_code = invoice_lines[0]['zone']
        previous_total = sum((l['commission'] for l in invoice_lines), Decimal('0'))
        if override.excluded:
            zone_totals[zone_code] -= previous_total
            result_lines.extend({**l, 'commission': Decimal('0'), 'excluded': True} for l in invoice_lines)
        elif override.override_amount is not None:
            zone_totals[zone_code] -= previous_total
            zone_totals[override.zone or zone_code] += override.override_amount
            result_lines.append(_manual_line(invoice_lines[0], override))
        else:
            result_lines.extend(invoice_lines)

    present_ids = set(lines_by_invoice.keys())
    added = [
        (invoice_id, o) for invoice_id, o in overrides.items()
        if invoice_id not in present_ids and not o.excluded and o.override_amount is not None
    ]
    if added:
        facturas = {
            f['CIDDOCUMENTO']: f for f in AdmDocumentos.objects.filter(
                CIDDOCUMENTO__in=[invoice_id for invoice_id, _ in added]
            ).values('CIDDOCUMENTO', 'CFOLIO', 'CIDCLIENTEPROVEEDOR', 'CRAZONSOCIAL', 'CFECHA')
        }
        for invoice_id, override in added:
            factura = facturas.get(invoice_id)
            if factura is None or not override.zone:
                continue
            zone_totals[override.zone] += override.override_amount
            result_lines.append(_manual_line({
                'invoice_id': invoice_id,
                'folio': factura['CFOLIO'],
                'client_id': factura['CIDCLIENTEPROVEEDOR'],
                'cliente': factura['CRAZONSOCIAL'],
                'zone': override.zone,
                'paid_date': factura['CFECHA'],
                'due_date': None,
                'days_late': 0,
            }, override))

    return result_lines


def calculate_commissions(date_from, date_to, lookback_days=DEFAULT_LOOKBACK_DAYS):
    """Commission calc for Facturas that became fully paid within
    [date_from, date_to] (both `datetime.date`) - not invoices merely dated
    in that range, since no commission is earned until an invoice is paid
    off in full (confirmed by management: partial payments earn nothing).

    The paid date is the Contabilidad (ledger) date, never Comercial's.
    Returns per-zone totals, a per-line-item drilldown, and the fully-paid
    invoices the ledger can't date (~0.4% of paid invoices since 2025) -
    accepted by management as a manual-review bucket rather than guessed at.
    """
    floor_date = date_from - timedelta(days=lookback_days)
    # Unpaid candidates are only needed by the ledger attribution below.
    candidates = CommissionRepository.fetch_scoped_facturas(floor_date, date.today())
    # Cents-sized placeholder invoices: nothing to collect, nothing to earn.
    all_facturas = [
        f for f in candidates
        if f['CPENDIENTE'] == 0 and (f['CTOTAL'] or 0) >= LEDGER_FULL_PAYMENT_TOLERANCE
    ]

    # How Comercial settled each invoice - money vs credit notes/returns -
    # from its exact payment-to-invoice record. Settled with no money at all
    # means not commission-eligible (confirmed by management), so those are
    # pulled out before payment-date resolution and never land in the
    # "needs manual review" bucket either. Until 2026-09-28 this was guessed
    # by matching returns to invoices by client and amount, which missed
    # every invoice settled by a Nota de Credito (14 since 2025) and wrongly
    # excluded 3 invoices paid entirely in cash (e.g. folio 17859, $33,279.57).
    settlements = CommissionRepository.fetch_settlements(floor_date)

    def settled_without_money(f):
        s = settlements.get(f['CIDDOCUMENTO'])
        return s is not None and s['cash'] < LEDGER_FULL_PAYMENT_TOLERANCE and s['credit'] >= LEDGER_FULL_PAYMENT_TOLERANCE

    credit_noted = [f for f in all_facturas if settled_without_money(f)]
    facturas = [f for f in all_facturas if not settled_without_money(f)]

    # Punto de Venta invoices are subdistributor clients, not office walk-ins
    # (confirmed by management 2026-09-19) - their commission belongs to
    # whichever route salesperson (ZONA1/ZONA2) is responsible for that
    # client, at the flat PUNTOVENTA rate, not the usual per-category one.
    # Nothing in the ERP records that assignment (checked admClientes.
    # CIDAGENTEVENTA/CIDAGENTECOBRO - 99.8% of these clients are just
    # "PUNTOVENTA" there too), so it's app-owned config
    # (PuntoVentaClientZone). Invoices whose client isn't in that mapping
    # yet are pulled out here, before payment-date resolution, same as
    # credit-noted ones - a missing zone assignment is a different problem
    # from a missing payment date and shouldn't get lumped into that bucket.
    agent_codes = CommissionRepository.fetch_agent_codes()
    puntoventa_client_zones = CommissionRepository.fetch_puntoventa_client_zones()
    puntoventa_zone_override = {}
    puntoventa_unassigned = []
    _facturas = []
    for f in facturas:
        origin_zone = agent_codes.get(f['CIDAGENTE'])
        if origin_zone == PUNTOVENTA_ZONE_NAME:
            reassigned_zone = puntoventa_client_zones.get(f['CIDCLIENTEPROVEEDOR'])
            if reassigned_zone:
                puntoventa_zone_override[f['CIDDOCUMENTO']] = reassigned_zone
                _facturas.append(f)
            else:
                puntoventa_unassigned.append(f)
        else:
            _facturas.append(f)
    facturas = _facturas

    # The paid date is ONLY ever the Contabilidad date: a commission is earned
    # once the payment is officially in Contpaq (decided by management
    # 2026-09-28 - e.g. a post-dated cheque registered in Comercial doesn't
    # count until its poliza exists). The Comercial-side date that used to
    # fill the gaps is gone; what the ledger can't date goes to manual review.
    # An invoice partly settled by a credit note/return is paid once the
    # ledger covers the part that was settled with money.
    concepto_series = CommissionRepository.fetch_concepto_series()
    ledger_lines = CommissionRepository.fetch_ledger_payment_lines(floor_date)
    accepted = attribute_ledger_payments(candidates, ledger_lines, concepto_series)
    cash_due = {
        invoice_id: s['cash'] for invoice_id, s in settlements.items() if s['credit'] >= LEDGER_FULL_PAYMENT_TOLERANCE
    }
    paid_dates = _paid_dates_from_ledger(facturas, accepted, cash_due)

    facturas_by_id = {f['CIDDOCUMENTO']: f for f in facturas}
    in_period_ids = [
        invoice_id for invoice_id, paid_date in paid_dates.items()
        if date_from <= paid_date.date() <= date_to
    ]
    unresolved = [f for f in facturas if f['CIDDOCUMENTO'] not in paid_dates]

    movimientos = CommissionRepository.fetch_movimientos(in_period_ids)
    product_ids = {m['CIDPRODUCTO'] for m in movimientos}
    productos_by_id = {p['CIDPRODUCTO']: p for p in CommissionRepository.fetch_productos(product_ids)}
    brand_names = CommissionRepository.fetch_brand_names()

    zero_codes = set(ZeroCommissionProduct.objects.filter(active=True).values_list('producto_codigo', flat=True))
    rates_by_code = {r.code: r for r in CommissionCategoryRate.objects.filter(active=True)}

    lines = []
    zone_totals = defaultdict(Decimal)

    for m in movimientos:
        factura = facturas_by_id[m['CIDDOCUMENTO']]
        producto = productos_by_id.get(m['CIDPRODUCTO'])
        if producto is None:
            continue

        category = _classify_line(producto, brand_names, zero_codes)
        reassigned_zone = puntoventa_zone_override.get(m['CIDDOCUMENTO'])
        if reassigned_zone:
            # Flat Punto de Venta rate overrides the usual per-category one
            # regardless of what the product is - category is still shown
            # in the drilldown for transparency, just not used for the rate.
            zone_code = reassigned_zone
            rate_code = None if category == 'ZERO' else PUNTOVENTA_RATE_CODE
        else:
            zone_code = agent_codes.get(factura['CIDAGENTE'])
            rate_code = _rate_code_for(category, zone_code)
        rate_row = rates_by_code.get(rate_code) if rate_code else None

        paid_date = paid_dates[m['CIDDOCUMENTO']]
        due_date = factura['CFECHAVENCIMIENTO']
        days_late = (paid_date - due_date).days if due_date else 0

        rate = _effective_rate(rate_row, days_late)
        # CNETO is pre-discount (verified against real data 2026-09-19: a
        # $64,192 line with an 8% discount posts CNETO=64192, CTOTAL=59,056.64
        # - commission was being computed on the undiscounted price, real
        # money on ~11% of lines that carry any discount). Subtract the
        # line's own discounts to get the actual, pre-tax amount the client
        # was charged - matches CTOTAL - tax exactly, confirmed against
        # taxed+discounted lines too.
        discount = sum(Decimal(str(m[f'CDESCUENTO{i}'] or 0)) for i in range(1, 6))
        net_amount = Decimal(str(m['CNETO'])) - discount
        commission = net_amount * rate
        quantity = Decimal(str(m['CUNIDADES']))
        unit_amount = net_amount / quantity if quantity else None

        zone_totals[zone_code] += commission
        lines.append({
            'invoice_id': m['CIDDOCUMENTO'],
            'folio': factura['CFOLIO'],
            'client_id': factura['CIDCLIENTEPROVEEDOR'],
            'cliente': factura['CRAZONSOCIAL'],
            'zone': zone_code,
            'producto_codigo': producto['CCODIGOPRODUCTO'],
            'producto_nombre': producto['CNOMBREPRODUCTO'],
            'category': category,
            'rate_code': rate_code,
            'quantity': quantity,
            'unit_amount': unit_amount,
            'net_amount': net_amount,
            'rate': rate,
            'days_late': days_late,
            'paid_date': paid_date,
            'due_date': due_date,
            'commission': commission,
        })

    overrides = CommissionRepository.fetch_overrides()
    if overrides:
        lines = _apply_overrides(lines, zone_totals, overrides)

    return {
        'date_from': date_from,
        'date_to': date_to,
        'zone_totals': dict(zone_totals),
        'lines': lines,
        'unresolved_payment_date': {
            'count': len(unresolved),
            'total_amount': sum((Decimal(str(f['CTOTAL'])) for f in unresolved), Decimal('0')),
            'note': (
                'Facturas saldadas en Comercial cuyo pago Contabilidad no registra completo: sin fecha '
                'oficial de pago, así que no entran en los totales. Revíselas en Contpaqi (casi siempre '
                'falta una póliza o cita otro folio). Incluye facturas emitidas desde 12 meses antes '
                'de este mes, no solo las de este mes.'
            ),
        },
        'credit_noted': {
            'count': len(credit_noted),
            'total_amount': sum((Decimal(str(f['CTOTAL'])) for f in credit_noted), Decimal('0')),
            'note': (
                'Facturas saldadas solo con notas de crédito o devoluciones, sin pago en dinero: no '
                'generan comisión (confirmado por gerencia). Incluye facturas emitidas desde 12 meses '
                'antes de este mes, no solo las de este mes.'
            ),
        },
        'puntoventa_unassigned': {
            'count': len(puntoventa_unassigned),
            'total_amount': sum((Decimal(str(f['CTOTAL'])) for f in puntoventa_unassigned), Decimal('0')),
            'note': (
                'Facturas de Punto de Venta cuyo cliente aún no tiene zona asignada (Zona 1 o Zona 2): '
                'su comisión no se paga a nadie hasta asignarla en el admin (PuntoVentaClientZone).'
            ),
        },
    }
