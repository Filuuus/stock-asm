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
from datetime import date, timedelta, timezone as dt_timezone
from decimal import Decimal

from django.db import connections
from django.utils import timezone as dj_timezone

from api.models import AdmAgentes, AdmClasificacionesValores, AdmConceptos, AdmDocumentos, AdmMovimientos, AdmProductos

from .models import CommissionCategoryRate, InvoiceCommissionOverride, PuntoVentaClientZone, ZeroCommissionProduct

FACTURA_DOC_TYPE = 4
DEVOLUCION_DOC_TYPE = 5  # Devolucion sobre Venta - a return/credit note against a Factura, not a real sale.
PAGO_DOC_TYPES = (9, 10, 12)

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

# How close a Devolucion's date can be to a Factura's own date for the
# same-client/same-amount fallback match below (see _find_credit_noted_invoices).
DEVOLUCION_FALLBACK_WINDOW_DAYS = 10
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
# period. 120 days comfortably covers the observed late-payment tail
# (verified against real data: the 90+-days-late bucket is small).
DEFAULT_LOOKBACK_DAYS = 120

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
    def fetch_paid_facturas(floor_date):
        return list(
            AdmDocumentos.objects.filter(
                CIDDOCUMENTODE=FACTURA_DOC_TYPE,
                CCANCELADO=0,
                CPENDIENTE=0,
                CIDAGENTE__in=ZONE_SCOPE.values(),
                CFECHA__date__gte=floor_date,
            ).values(
                'CIDDOCUMENTO', 'CFOLIO', 'CFECHA', 'CFECHAVENCIMIENTO',
                'CIDCLIENTEPROVEEDOR', 'CRAZONSOCIAL', 'CIDAGENTE', 'CTOTAL', 'CIDCONCEPTODOCUMENTO',
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
        CPENDIENTE - unlike fetch_paid_facturas, being currently unpaid
        doesn't disqualify a Factura here, since we're matching against
        historical ledger/payment events dated in the window, not today's
        live balance.
        """
        floor_date = date_from - timedelta(days=candidate_lookback_days)
        return list(
            AdmDocumentos.objects.filter(
                CIDDOCUMENTODE=FACTURA_DOC_TYPE,
                CCANCELADO=0,
                CIDAGENTE__in=ZONE_SCOPE.values(),
                CFECHA__date__gte=floor_date,
                CFECHA__date__lte=date_to,
            ).values(
                'CIDDOCUMENTO', 'CFOLIO', 'CFECHA', 'CFECHAVENCIMIENTO', 'CTOTAL',
                'CIDCLIENTEPROVEEDOR', 'CRAZONSOCIAL', 'CIDAGENTE', 'CIDCONCEPTODOCUMENTO',
            )
        )

    @staticmethod
    def fetch_payment_docs(floor_date):
        # Searched from the invoice lookback floor through TODAY - never
        # capped at the report's date_to. Capping it there was a real bug:
        # for an invoice settled via several installments in different
        # months, _resolve_payment_dates takes the latest payment found
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
    def fetch_devoluciones(floor_date):
        return list(
            AdmDocumentos.objects.filter(
                CIDDOCUMENTODE=DEVOLUCION_DOC_TYPE,
                CFECHA__date__gte=floor_date,
                CFECHA__date__lte=date.today(),
            ).values('CIDDOCUMENTO', 'CFECHA', 'CIDCLIENTEPROVEEDOR', 'CTOTAL', 'CIDDOCUMENTOORIGEN')
        )

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
    def fetch_ledger_payments(floor_date):
        """Raw cross-database read against the Contabilidad ledger (see
        LEDGER_DATABASE above) - still read-only, just not expressible
        through the Django ORM since it's a second database on the same
        SQL Server rather than a model in this app. COLLATE DATABASE_DEFAULT
        is required on the join or MSSQL refuses it with a collation-
        conflict error between the two databases' default collations.
        """
        with connections['erp'].cursor() as cursor:
            cursor.execute(
                f"""
                SELECT LTRIM(RTRIM(mp.Referencia)), mp.Fecha, mp.Concepto, mp.Importe, mp.TipoMovto
                FROM {LEDGER_DATABASE}.dbo.MovimientosPoliza mp
                JOIN {LEDGER_DATABASE}.dbo.Polizas p ON p.Id = mp.IdPoliza
                WHERE p.Concepto = %s AND mp.Fecha >= %s AND mp.Fecha <= %s
                  AND mp.Referencia IS NOT NULL AND mp.Referencia <> ''
                """,
                [LEDGER_PAGO_CONCEPTO, floor_date, date.today()],
            )
            return cursor.fetchall()

    @staticmethod
    def fetch_ledger_payment_lines(floor_date):
        """Every MovimientosPoliza line for PAGO DEL CLIENTE polizas in the
        window - unlike fetch_ledger_payments above, this does NOT filter
        out blank-Referencia lines. Those are the OTHER side of the same
        journal entry: the one that debits the real bank account the money
        landed in (see corte_de_caja/services.py, which is the only
        consumer of this - commissions itself only ever needed the
        referenced/matchable lines). Checked live 2026-09-24: every real
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
                WHERE p.Concepto = %s AND mp.Fecha >= %s AND mp.Fecha <= %s
                """,
                [LEDGER_PAGO_CONCEPTO, floor_date, date.today()],
            )
            return cursor.fetchall()

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


def _resolve_payment_dates(facturas, payment_docs):
    """FALLBACK ONLY as of 2026-09-17 - see _resolve_payment_dates_from_ledger
    below, which is tried first and is far more reliable. Kept for the
    handful of invoices the ledger doesn't cover.

    Match payment docs to invoices by (folio, client) - CREFERENCIA is
    free text typed by whoever recorded the payment, so the folio number
    plus client is the reliable key (verified: matching the typed prefix
    against admConceptos only succeeds ~44% of the time due to typos/
    abbreviations, while folio+client resolves correctly ~99.9% of the
    time). Returns {invoice_id: paid_date}, taking the LATEST referencing
    payment when an invoice has multiple installments (~7% of cases).
    """
    by_folio_client = defaultdict(list)
    for f in facturas:
        by_folio_client[(int(f['CFOLIO']), f['CIDCLIENTEPROVEEDOR'])].append(f['CIDDOCUMENTO'])

    paid_dates = {}
    for pago in payment_docs:
        cliente = pago['CIDCLIENTEPROVEEDOR']
        for token in _extract_folio_tokens(pago['CREFERENCIA']):
            invoice_ids = by_folio_client.get((int(token), cliente))
            if not invoice_ids:
                continue
            for invoice_id in invoice_ids:
                existing = paid_dates.get(invoice_id)
                if existing is None or pago['CFECHA'] > existing:
                    paid_dates[invoice_id] = pago['CFECHA']
    return paid_dates


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


def _resolve_payment_dates_from_ledger(facturas, ledger_rows, concepto_series):
    """PRIMARY payment-date source (2026-09-17): the Contpaqi Contabilidad
    ledger (see LEDGER_DATABASE) mirrors every sale/payment as an accounting
    entry with a clean folio reference - even bulk payments covering several
    invoices get one itemized line per invoice there, unlike the Comercial
    side's free-text CREFERENCIA which is sometimes blank and sometimes
    lists only some of the invoices a bulk payment actually covers. Verified
    against three real cases the user found by hand in Contpaqi, and raised
    September's resolution rate from 84% to 96%.

    The ledger's Referencia is built as "{serie}-{folio}" or "{serie} {folio}"
    (both forms seen in real data, inconsistently) where serie is the tax
    series (A/B/F) - NOT the display prefix, which is always "F" regardless
    of series (see AdmConceptos.CSERIEPOROMISION vs CPREFIJOCONCEPTO).

    Folio+serie collisions happen (two different clients can share a folio,
    and old unrelated transactions going back to 2017 have reused the exact
    same reference text), so results are cross-checked against the client
    name in the ledger entry's own Concepto field (accent/case-normalized,
    substring match - the two systems store the same razon social text,
    just not always identically formatted).

    CRITICAL - installments and full-payment verification: a large invoice
    can be settled via several dated entries under the same reference (each
    one two or three netted debit/credit lines - True/False on TipoMovto -
    that sum to the real installment amount). The first cut of this function
    just took the LATEST matching entry's date, same mistake as the old
    fallback method it was meant to fix: found 2026-09-17 on a real
    $5,300,000 ZONA2 invoice (CIDDOCUMENTO 100223) where the matching
    entries - Dec 30 $500k, Jan 30 $1M, Feb 27 $500k, Jun 30 $799,999.98 -
    only sum to ~$2.8M, nowhere near the full $5.3M (this client has a
    running-account arrangement with a persistent unexplained balance gap,
    found earlier during a FIFO-simulation investigation). Taking "Jun 30,
    the latest one found" as the full-payment date would have been just as
    unverified a guess as the old method's "Feb 27, the latest one it could
    parse" - neither is proven to be when the invoice actually hit zero.

    So: entries are netted per date (signed by TipoMovto: True adds, False
    subtracts - verified against real data, e.g. Dec 30's three lines net to
    exactly the $500,000 installment also visible on the Comercial side),
    sorted chronologically, and walked as a running total. Only the FIRST
    date where the cumulative total reaches the Factura's own CTOTAL (within
    LEDGER_FULL_PAYMENT_TOLERANCE) is accepted as the paid date. If the
    matched entries never reach the full total, this invoice is left
    unresolved by the ledger entirely (not resolved to a wrong, too-early
    date) - it falls through to the Comercial-side fallback method, or ends
    up in the manual-review bucket if that can't resolve it either.

    Returns {invoice_id: paid_date}.
    """
    # fecha comes back naive from the raw cross-database cursor (Django's
    # ORM-level timezone conversion only applies to QuerySets, not raw SQL),
    # but everything else in this module (USE_TZ=True) is timezone-aware -
    # without this, subtracting paid_date - due_date later raises
    # "can't subtract offset-naive and offset-aware datetimes".
    by_reference = defaultdict(list)
    for referencia, fecha, concepto, importe, tipo_movto in ledger_rows:
        if dj_timezone.is_naive(fecha):
            fecha = dj_timezone.make_aware(fecha, dt_timezone.utc)
        signed_amount = importe if tipo_movto else -importe
        by_reference[referencia.upper()].append((fecha, _normalize_name(concepto), signed_amount))

    paid_dates = {}
    for f in facturas:
        serie = concepto_series.get(f['CIDCONCEPTODOCUMENTO'], 'F')
        folio = int(f['CFOLIO'])
        client_name = _normalize_name(f['CRAZONSOCIAL'])
        total = f['CTOTAL'] or 0

        by_date = defaultdict(float)
        for referencia in (f'{serie}-{folio}'.upper(), f'{serie} {folio}'.upper()):
            for fecha, ledger_client_name, signed_amount in by_reference.get(referencia, []):
                if client_name and client_name not in ledger_client_name:
                    continue
                by_date[fecha] += signed_amount
        if not by_date:
            continue

        cumulative = 0.0
        for fecha in sorted(by_date):
            cumulative += by_date[fecha]
            if cumulative >= total - LEDGER_FULL_PAYMENT_TOLERANCE:
                paid_dates[f['CIDDOCUMENTO']] = fecha
                break
    return paid_dates


def _find_credit_noted_invoices(facturas, devoluciones):
    """Invoices settled by a credit note (Devolucion sobre Venta) rather
    than a real payment - confirmed by management these don't earn
    commission. Two ways a Devolucion links back to a Factura, found by
    manually cross-checking a real case (2026-09-17, CIDDOCUMENTO 105153,
    $1,885,012.50, EDUARDO GALLARDO DE ALBA):

    1. Direct: `CIDDOCUMENTOORIGEN` on the Devolucion points straight at
       the Factura it reverses - reliable when populated. In the checked
       case this pointed at an OLDER invoice for the exact same client and
       amount (apparently superseded/reissued), not at 105153 itself, so
       this alone doesn't catch every case.
    2. Fallback: same client + an exact-to-the-cent matching CTOTAL + a
       Devolucion dated within DEVOLUCION_FALLBACK_WINDOW_DAYS of the
       Factura. Amount-only matching is normally too weak to trust (see
       the ~16% amount-collision rate found earlier for regular payments),
       but a Devolucion for the exact same large amount within days of the
       invoice is a much stronger, rarer coincidence than an everyday
       payment - this is how 105153 itself gets caught, since its direct
       link points elsewhere.

    CRITICAL: both paths require the Devolucion's CTOTAL to match the
    Factura's CTOTAL almost exactly (full reversal), not just any
    Devolucion referencing it. First cut of this function excluded a
    Factura on ANY CIDDOCUMENTOORIGEN match regardless of amount, which
    wrongly zeroed out commission on invoices with only a PARTIAL credit
    note applied (e.g. a $5,259 return against a $12,271 invoice that was
    otherwise genuinely paid in cash) - caught during verification: those
    invoices already had a real resolved payment date before this
    exclusion was added. A partial credit note doesn't mean the invoice
    earned zero commission, just less - proportional handling is out of
    scope for this draft, so partially-credit-noted invoices are left
    alone entirely (still go through normal payment-date resolution) and
    only a FULL reversal is auto-excluded.

    Returns the set of Factura CIDDOCUMENTO values to treat as not
    commission-eligible at all (excluded from both the totals and the
    "needs manual review" bucket, not guessed at further).
    """
    facturas_by_id = {f['CIDDOCUMENTO']: f for f in facturas}
    credit_noted = set()

    by_client = defaultdict(list)
    for f in facturas:
        by_client[f['CIDCLIENTEPROVEEDOR']].append(f)

    def is_full_reversal(factura, devolucion_total):
        return abs((factura['CTOTAL'] or 0) - (devolucion_total or 0)) < 0.01

    for d in devoluciones:
        origen = d['CIDDOCUMENTOORIGEN']
        if origen and origen in facturas_by_id and is_full_reversal(facturas_by_id[origen], d['CTOTAL']):
            credit_noted.add(origen)
            continue

        total = d['CTOTAL']
        if not total:
            continue
        for f in by_client.get(d['CIDCLIENTEPROVEEDOR'], []):
            if f['CIDDOCUMENTO'] in credit_noted:
                continue
            if is_full_reversal(f, total) and \
                    abs((d['CFECHA'] - f['CFECHA']).days) <= DEVOLUCION_FALLBACK_WINDOW_DAYS:
                credit_noted.add(f['CIDDOCUMENTO'])

    return credit_noted


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
            ).values('CIDDOCUMENTO', 'CFOLIO', 'CRAZONSOCIAL', 'CFECHA')
        }
        for invoice_id, override in added:
            factura = facturas.get(invoice_id)
            if factura is None or not override.zone:
                continue
            zone_totals[override.zone] += override.override_amount
            result_lines.append(_manual_line({
                'invoice_id': invoice_id,
                'folio': factura['CFOLIO'],
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

    Returns per-zone totals, a per-line-item drilldown, and a count of
    fully-paid invoices whose payment date couldn't be traced (~4% of paid
    invoices in the verified sample, down from ~16% before the Contabilidad
    ledger became the primary resolution source - accepted by management as
    a manual-
    review bucket rather than guessed at).
    """
    floor_date = date_from - timedelta(days=lookback_days)
    all_facturas = CommissionRepository.fetch_paid_facturas(floor_date)
    devoluciones = CommissionRepository.fetch_devoluciones(floor_date)
    credit_noted_ids = _find_credit_noted_invoices(all_facturas, devoluciones)

    # Settled by a credit note, not a real payment - not commission-eligible
    # at all (confirmed by management). Pulled out before payment-date
    # resolution so they never land in the "needs manual review" bucket
    # either - we already know why they have no traceable payment.
    credit_noted = [f for f in all_facturas if f['CIDDOCUMENTO'] in credit_noted_ids]
    facturas = [f for f in all_facturas if f['CIDDOCUMENTO'] not in credit_noted_ids]

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

    payment_docs = CommissionRepository.fetch_payment_docs(floor_date)
    paid_dates_fallback = _resolve_payment_dates(facturas, payment_docs)

    concepto_series = CommissionRepository.fetch_concepto_series()
    ledger_rows = CommissionRepository.fetch_ledger_payments(floor_date)
    paid_dates_ledger = _resolve_payment_dates_from_ledger(facturas, ledger_rows, concepto_series)

    # Ledger wins on overlap - it's the authoritative accounting record, the
    # Comercial-side CREFERENCIA guess is only a fallback for what it misses.
    paid_dates = {**paid_dates_fallback, **paid_dates_ledger}

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
                'Facturas fully paid per CPENDIENTE=0 but with no traceable payment date - '
                'excluded from the totals above, needs manual review.'
            ),
        },
        'credit_noted': {
            'count': len(credit_noted),
            'total_amount': sum((Decimal(str(f['CTOTAL'])) for f in credit_noted), Decimal('0')),
            'note': (
                'Facturas settled by a Devolucion sobre Venta (credit note), not a real payment - '
                'confirmed by management these do not earn commission. Excluded entirely, not counted '
                'as needing manual review.'
            ),
        },
        'puntoventa_unassigned': {
            'count': len(puntoventa_unassigned),
            'total_amount': sum((Decimal(str(f['CTOTAL'])) for f in puntoventa_unassigned), Decimal('0')),
            'note': (
                'Punto de Venta invoices (subdistributor clients) whose responsible salesperson '
                '(ZONA1/ZONA2) is not yet configured - add them in the admin (PuntoVentaClientZone) '
                'to include their commission.'
            ),
        },
    }
