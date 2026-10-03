"use client";

import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import {
  Ban,
  ChevronDown,
  ChevronRight,
  Loader2,
  Plus,
  RotateCcw,
  X,
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import InvoiceLink from "@/components/facturas/InvoiceLink";
import ClientLink from "@/components/facturas/ClientLink";
import { HIDE_BELOW_LG, HIDE_BELOW_SM, SortableHead, SortColumn, useSort, EmptyRow } from "@/components/sortable-table";
import { MonthControl } from "@/components/date-controls";
import { currentMonthISO, formatDay } from "@/lib/dates";
import { ZONE_LABELS } from "@/lib/zones";
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn, formatMoney, plural } from "@/lib/utils";
import { Notice, NoticeList } from "@/components/notice";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/hooks/use-auth";
import { CommissionLine, CommissionsSummary, InvoiceSearchResult, WarningInvoice, Zone } from "@/types/commissions";

const CATEGORY_LABELS: Record<string, string> = {
  R: "Refacciones",
  R_NW: "Refacciones (Tapetes y pernos)",
  R_CHEM: "Refacciones (Químicos)",
  R_FAN: "Refacciones (Ventiladores)",
  B: "Bionat",
  B_MIPRO: "Bionat (Mipro)",
  B_BOVI: "Bionat (Bovifit)",
  S: "Servicios",
  ZERO: "Sin comisión",
};

const CATEGORY_BADGE: Record<string, string> = {
  R: "bg-blue-100 text-blue-800 border-blue-200",
  R_NW: "bg-sky-100 text-sky-800 border-sky-200",
  R_CHEM: "bg-cyan-100 text-cyan-800 border-cyan-200",
  R_FAN: "bg-indigo-100 text-indigo-800 border-indigo-200",
  B: "bg-green-100 text-green-800 border-green-200",
  B_MIPRO: "bg-emerald-100 text-emerald-800 border-emerald-200",
  B_BOVI: "bg-lime-100 text-lime-800 border-lime-200",
  S: "bg-purple-100 text-purple-800 border-purple-200",
  ZERO: "bg-gray-100 text-gray-600 border-gray-200",
};

interface InvoiceGroup {
  invoice_id: number;
  folio: number;
  folio_display: string;
  client_id: number;
  cliente: string;
  zone: Zone;
  paid_date: string;
  days_late: number;
  net_total: number;
  commission_total: number;
  excluded: boolean;
  manual: boolean;
  lines: CommissionLine[];
}

// Punto de Venta invoices earn for the zone that owns the client (see
// PuntoVentaClientZone), never for Punto de Venta itself.
const COMMISSION_ZONES = (Object.keys(ZONE_LABELS) as Zone[]).filter((z) => z !== "PUNTOVENTA");

// Invoices listed inside a warning: date, invoice, client, zone, total.
function InvoiceList({ rows, dateLabel }: { rows: WarningInvoice[]; dateLabel: string }) {
  return (
    <NoticeList
      rows={rows}
      rowKey={(r) => r.invoice_id}
      columns={[
        { label: "Factura", cell: (r) => <span className="num"><InvoiceLink invoiceId={r.invoice_id} label={r.folio_display} /></span> },
        { label: "Cliente", cell: (r) => <ClientLink clientId={r.client_id} label={r.cliente} /> },
        { label: dateLabel, cell: (r) => formatDay(r.date) },
        { label: "Zona", cell: (r) => ZONE_LABELS[r.zone] ?? r.zone },
        { label: "Total", cell: (r) => <span className="num">{formatMoney(r.total)}</span>, align: "right" },
      ]}
    />
  );
}


function quantity(value: number) {
  return value.toLocaleString("es-MX", { maximumFractionDigits: 2 });
}

// month is "YYYY-MM" - commissions are always calculated one calendar month
// at a time, based on when payment was received.
function monthRange(month: string) {
  const [year, m] = month.split("-").map(Number);
  const lastDay = new Date(year, m, 0).getDate();
  return {
    from: `${month}-01`,
    to: `${month}-${String(lastDay).padStart(2, "0")}`,
  };
}

function groupByInvoice(lines: CommissionLine[]): InvoiceGroup[] {
  const groups = new Map<number, InvoiceGroup>();
  for (const line of lines) {
    let group = groups.get(line.invoice_id);
    if (!group) {
      group = {
        invoice_id: line.invoice_id,
        folio: line.folio,
        folio_display: line.folio_display,
        client_id: line.client_id,
        cliente: line.cliente,
        zone: line.zone,
        paid_date: line.paid_date,
        days_late: line.days_late,
        net_total: 0,
        commission_total: 0,
        excluded: false,
        manual: false,
        lines: [],
      };
      groups.set(line.invoice_id, group);
    }
    group.net_total += line.net_amount;
    group.commission_total += line.commission;
    if (line.excluded) group.excluded = true;
    if (line.manual) group.manual = true;
    group.lines.push(line);
  }
  return [...groups.values()];
}

type InvoiceSortKey = "folio" | "cliente" | "zona" | "paid_date" | "days_late" | "items" | "commission";

const INVOICE_SORT: Record<InvoiceSortKey, SortColumn<InvoiceGroup>> = {
  folio: { value: (g) => g.folio, first: "desc" },
  cliente: { value: (g) => g.cliente, first: "asc" },
  zona: { value: (g) => ZONE_LABELS[g.zone] ?? g.zone, first: "asc" },
  paid_date: { value: (g) => g.paid_date, first: "desc" },
  days_late: { value: (g) => g.days_late, first: "desc" },
  items: { value: (g) => g.lines.length, first: "desc" },
  commission: { value: (g) => g.commission_total, first: "desc" },
};

const byFolioDesc = (a: InvoiceGroup, b: InvoiceGroup) => b.folio - a.folio;

export default function CommissionsView() {
  const { loading: authLoading, isWorker, isManagement } = useAuth();
  const [month, setMonth] = useState(currentMonthISO);
  const [data, setData] = useState<CommissionsSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [selectedZone, setSelectedZone] = useState<Zone | null>(null);

  const [addOpen, setAddOpen] = useState(false);
  const [searchFolio, setSearchFolio] = useState("");
  const [searchResults, setSearchResults] = useState<InvoiceSearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [selectedInvoice, setSelectedInvoice] = useState<InvoiceSearchResult | null>(null);
  const [overrideAmount, setOverrideAmount] = useState("");
  const [overrideZone, setOverrideZone] = useState<Zone | "">("");
  const [overrideNote, setOverrideNote] = useState("");
  const [overrideSubmitting, setOverrideSubmitting] = useState(false);
  const [overrideError, setOverrideError] = useState<string | null>(null);

  // Per-line rate edit (LineRateOverride): rate typed as a percentage.
  const [rateLine, setRateLine] = useState<CommissionLine | null>(null);
  const [ratePercent, setRatePercent] = useState("");
  const [rateNote, setRateNote] = useState("");
  const [rateSaving, setRateSaving] = useState(false);
  const [rateError, setRateError] = useState<string | null>(null);

  const requestIdRef = useRef(0);

  const fetchSummary = async (targetMonth: string) => {
    // Never fetch a malformed month: the old native <input type="month">
    // fired onChange with half-typed values ("2026-0"), which crashed the
    // backend's date parser (found live 2026-09-17). The month picker only
    // emits whole months now, but the guard is cheap. requestId keeps an
    // older response from overwriting a newer one.
    if (!/^\d{4}-\d{2}$/.test(targetMonth)) return;

    const requestId = ++requestIdRef.current;
    setLoading(true);
    setError(null);
    try {
      const { from, to } = monthRange(targetMonth);
      const res = await apiFetch(
        `/api/commissions/summary/?date_from=${from}&date_to=${to}`,
        { cache: "no-store" },
      );
      if (!res.ok) throw new Error(`El servidor respondió ${res.status}`);
      const json = await res.json();
      if (requestId !== requestIdRef.current) return;
      setData(json);
    } catch (err) {
      if (requestId !== requestIdRef.current) return;
      setError(
        err instanceof Error ? err.message : "No se pudo cargar la información",
      );
    } finally {
      if (requestId === requestIdRef.current) setLoading(false);
    }
  };

  useEffect(() => {
    if (!isWorker) return;
    // fetchSummary sets loading/error state synchronously before its first
    // await - standard fetch-on-mount pattern, safe to disable here.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchSummary(month);
    // Intentionally run once auth resolves - handleMonthChange covers refetches.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isWorker]);

  const handleMonthChange = (value: string) => {
    setMonth(value);
    fetchSummary(value);
  };

  const handleZoneClick = (zone: Zone) => {
    setSelectedZone((prev) => (prev === zone ? null : zone));
  };

  const toggleExpanded = (invoiceId: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(invoiceId)) next.delete(invoiceId);
      else next.add(invoiceId);
      return next;
    });
  };

  const openAddDialog = () => {
    setSearchFolio("");
    setSearchResults([]);
    setSearchError(null);
    setSelectedInvoice(null);
    setOverrideAmount("");
    setOverrideZone("");
    setOverrideNote("");
    setOverrideError(null);
    setAddOpen(true);
  };

  const handleSearch = async () => {
    if (!searchFolio.trim()) return;
    setSearching(true);
    setSearchError(null);
    try {
      const res = await apiFetch(`/api/commissions/invoices/search/?folio=${encodeURIComponent(searchFolio.trim())}`);
      const json = await res.json();
      if (!res.ok) throw new Error(json.error ?? "No se pudo buscar la factura.");
      setSearchResults(json);
      if (json.length === 0) setSearchError("Sin resultados para ese folio.");
    } catch (err) {
      setSearchError(err instanceof Error ? err.message : "No se pudo buscar la factura.");
    } finally {
      setSearching(false);
    }
  };

  const handleSelectInvoice = (invoice: InvoiceSearchResult) => {
    setSelectedInvoice(invoice);
    setOverrideZone(invoice.zone ?? "");
  };

  const submitOverride = async (body: Record<string, unknown>) => {
    const res = await apiFetch("/api/commissions/overrides/", {
      method: "POST",
      body: JSON.stringify(body),
    });
    const json = await res.json();
    if (!res.ok) throw new Error(json.error ?? "No se pudo guardar el ajuste.");
    return json;
  };

  const handleSubmitAdd = async () => {
    if (!selectedInvoice) return;
    if (!overrideAmount || !overrideZone) {
      setOverrideError("Indique el monto y la zona.");
      return;
    }
    setOverrideSubmitting(true);
    setOverrideError(null);
    try {
      await submitOverride({
        invoice_id: selectedInvoice.invoice_id,
        override_amount: overrideAmount,
        zone: overrideZone,
        note: overrideNote,
      });
      setAddOpen(false);
      fetchSummary(month);
    } catch (err) {
      setOverrideError(err instanceof Error ? err.message : "No se pudo guardar el ajuste.");
    } finally {
      setOverrideSubmitting(false);
    }
  };

  const handleToggleExclude = async (group: InvoiceGroup) => {
    try {
      // A manual-amount override also needs "Restaurar" to fully clear it
      // (not flip it to excluded=true) - otherwise there'd be no way back
      // to the automatic calculation from the dashboard, only via the
      // Django admin.
      if (group.excluded || group.manual) {
        const res = await apiFetch(`/api/commissions/overrides/${group.invoice_id}/`, { method: "DELETE" });
        if (!res.ok) throw new Error("No se pudo restaurar la factura.");
      } else {
        await submitOverride({ invoice_id: group.invoice_id, excluded: true });
      }
      fetchSummary(month);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo actualizar la factura.");
    }
  };

  const openRateDialog = (line: CommissionLine) => {
    setRateLine(line);
    setRatePercent(line.rate != null ? String(+(line.rate * 100).toFixed(2)) : "");
    setRateNote(line.rate_note ?? "");
    setRateError(null);
  };

  // rate = null restores the automatic rate.
  const saveLineRate = async (rate: number | null) => {
    if (!rateLine?.movimiento_id) return;
    setRateSaving(true);
    setRateError(null);
    try {
      const res =
        rate == null
          ? await apiFetch(`/api/commissions/line-rates/${rateLine.movimiento_id}/`, { method: "DELETE" })
          : await apiFetch("/api/commissions/line-rates/", {
              method: "POST",
              body: JSON.stringify({
                movimiento_id: rateLine.movimiento_id,
                invoice_id: rateLine.invoice_id,
                rate,
                note: rateNote,
              }),
            });
      if (!res.ok) {
        const json = await res.json().catch(() => ({}));
        throw new Error(json.error ?? "No se pudo guardar la tasa.");
      }
      setRateLine(null);
      fetchSummary(month);
    } catch (err) {
      setRateError(err instanceof Error ? err.message : "No se pudo guardar la tasa.");
    } finally {
      setRateSaving(false);
    }
  };

  const handleSaveRate = () => {
    const percent = Number(ratePercent);
    if (ratePercent.trim() === "" || !Number.isFinite(percent) || percent < 0 || percent > 20) {
      setRateError("Indique una tasa entre 0 y 20%.");
      return;
    }
    saveLineRate(percent / 100);
  };

  const totalCommission = useMemo(() => {
    if (!data) return 0;
    return Object.values(data.zone_totals).reduce(
      (sum, v) => sum + (v ?? 0),
      0,
    );
  }, [data]);

  const invoiceGroups = useMemo(() => {
    if (!data) return [];
    let groups = groupByInvoice(data.lines);
    if (selectedZone) {
      groups = groups.filter((g) => g.zone === selectedZone);
    }
    const q = filter.trim().toLowerCase();
    if (!q) return groups;
    return groups.filter(
      (g) =>
        `${g.cliente} ${g.folio} ${g.folio_display}`.toLowerCase().includes(q) ||
        g.lines.some((l) =>
          `${l.producto_nombre} ${l.producto_codigo ?? ""}`.toLowerCase().includes(q),
        ),
    );
  }, [data, filter, selectedZone]);
  const {
    sorted: sortedGroups,
    sortKey,
    sortDir,
    toggle: toggleSort,
  } = useSort(invoiceGroups, INVOICE_SORT, { key: "commission", dir: "desc" }, byFolioDesc);

  if (!authLoading && !isWorker) {
    return (
      <main className="max-w-7xl mx-auto w-full p-4 sm:p-6">
        <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-gray-300 bg-white py-16 text-center">
          <p className="text-sm font-medium text-gray-700">
            Debe iniciar sesión para ver las comisiones.
          </p>
          <a href="/login" className="text-sm font-medium text-slate-900 underline">
            Iniciar sesión
          </a>
        </div>
      </main>
    );
  }

  return (
    <main className="max-w-7xl mx-auto w-full p-4 sm:p-6 flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold text-gray-900">Comisiones</h1>
        <p className="text-sm text-gray-500">
          Cálculo automático a partir de facturas pagadas en su totalidad -
          borrador para revisión, no es el pago oficial.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <MonthControl month={month} onChange={handleMonthChange} />
        {(loading || authLoading) && (
          <Loader2 className="w-4 h-4 animate-spin text-gray-400" />
        )}
      </div>

      {error && <Notice tone="error" summary={error} />}

      {/* Old results stay visible, faded, while the next ones load. */}
      {data && !error && (
        <div className={cn("flex flex-col gap-6 transition-opacity", loading && "pointer-events-none opacity-50")}>
          <Card>
            <CardHeader>
              <CardDescription>
                Total de comisiones, {formatDay(data.date_from)} a {formatDay(data.date_to)}
              </CardDescription>
              <CardTitle className="text-3xl">
                {formatMoney(totalCommission)}
              </CardTitle>
            </CardHeader>
          </Card>

          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {COMMISSION_ZONES.map((zone) => (
              <Card
                key={zone}
                onClick={() => handleZoneClick(zone)}
                className={cn(
                  "cursor-pointer transition-colors hover:border-gray-400",
                  selectedZone === zone && "border-slate-900 ring-1 ring-slate-900",
                )}
              >
                <CardHeader className="p-4">
                  <CardDescription>{ZONE_LABELS[zone]}</CardDescription>
                  <CardTitle className="text-lg sm:text-xl">
                    {formatMoney(data.zone_totals[zone] ?? 0)}
                  </CardTitle>
                </CardHeader>
              </Card>
            ))}
          </div>

          {data.unresolved_payment_date.count > 0 && (
            <Notice
              tone="warning"
              title={`${plural(data.unresolved_payment_date.count, "factura pagada", "facturas pagadas")} en Comercial, aún sin póliza en Contabilidad (${formatMoney(data.unresolved_payment_date.total_amount)})`}
              summary="No entran en los totales hasta que se registre la póliza."
            >
              <p>{data.unresolved_payment_date.note}</p>
              <InvoiceList rows={data.unresolved_payment_date.rows} dateLabel="Pago en Comercial" />
            </Notice>
          )}

          {data.credit_noted.count > 0 && (
            <Notice
              tone="info"
              title={`${plural(data.credit_noted.count, "factura liquidada", "facturas liquidadas")} por nota de crédito este mes (${formatMoney(data.credit_noted.total_amount)})`}
              summary="No generan comisión."
            >
              <p>{data.credit_noted.note}</p>
              <InvoiceList rows={data.credit_noted.rows} dateLabel="Nota de crédito" />
            </Notice>
          )}

          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-semibold text-gray-900 whitespace-nowrap">
                  Facturas ({invoiceGroups.length})
                </h2>
                {selectedZone && (
                  <button
                    onClick={() => setSelectedZone(null)}
                    className="flex items-center gap-1 rounded-full bg-slate-900 px-2.5 py-1 text-xs font-medium text-white hover:bg-slate-700"
                  >
                    {ZONE_LABELS[selectedZone]}
                    <X className="w-3 h-3" />
                  </button>
                )}
              </div>
              <div className="flex items-center gap-2">
                {isManagement && (
                  <Button size="sm" variant="outline" onClick={openAddDialog} className="shrink-0">
                    <Plus className="w-4 h-4" />
                    Agregar factura
                  </Button>
                )}
                <Input
                  placeholder="Buscar cliente, producto o folio..."
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                  className="min-w-0 flex-1 sm:w-72 sm:flex-none"
                />
              </div>
            </div>

            <div className="rounded-lg border bg-white">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-8 px-2 sm:px-3" />
                    {(
                      [
                        ["folio", "Folio"],
                        ["cliente", "Cliente"],
                        ["zona", "Zona", undefined, HIDE_BELOW_LG],
                        ["paid_date", "Fecha de pago", undefined, HIDE_BELOW_SM],
                        ["days_late", "Días tarde", "right", HIDE_BELOW_LG],
                        ["items", "Productos", "right", HIDE_BELOW_LG],
                        ["commission", "Comisión", "right"],
                      ] as [InvoiceSortKey, string, "right"?, string?][]
                    ).map(([key, label, align, className]) => (
                      <SortableHead
                        key={key}
                        label={label}
                        column={key}
                        sortKey={sortKey}
                        sortDir={sortDir}
                        onSort={toggleSort}
                        align={align}
                        className={className}
                      />
                    ))}
                    {isManagement && <TableHead className={cn("w-28", HIDE_BELOW_SM)} />}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {sortedGroups.map((group) => {
                    const isOpen = expanded.has(group.invoice_id);
                    return (
                      <Fragment key={group.invoice_id}>
                        <TableRow
                          className={cn(
                            "cursor-pointer",
                            group.excluded && "opacity-50",
                            group.manual && "bg-amber-50",
                          )}
                          onClick={() => toggleExpanded(group.invoice_id)}
                        >
                          <TableCell className="px-2 sm:px-3">
                            {isOpen ? (
                              <ChevronDown className="w-4 h-4 text-gray-400" />
                            ) : (
                              <ChevronRight className="w-4 h-4 text-gray-400" />
                            )}
                          </TableCell>
                          <TableCell className={cn("num", group.excluded && "line-through")}>
                            <InvoiceLink invoiceId={group.invoice_id} label={group.folio_display} />
                          </TableCell>
                          <TableCell className={cn("max-w-28 sm:max-w-56 truncate", group.excluded && "line-through")}>
                            <ClientLink clientId={group.client_id} label={group.cliente} />
                          </TableCell>
                          <TableCell className={cn("text-gray-600 whitespace-nowrap", HIDE_BELOW_LG)}>
                            {ZONE_LABELS[group.zone] ?? group.zone}
                          </TableCell>
                          <TableCell className={cn("text-gray-600 whitespace-nowrap", HIDE_BELOW_SM)}>
                            {formatDay(group.paid_date)}
                          </TableCell>
                          <TableCell className={cn("text-right text-gray-600", HIDE_BELOW_LG)}>
                            {group.days_late > 0 ? group.days_late : "-"}
                          </TableCell>
                          <TableCell className={cn("text-right text-gray-600", HIDE_BELOW_LG)}>
                            {group.lines.length}
                          </TableCell>
                          <TableCell className="text-right num font-medium">
                            {formatMoney(group.commission_total)}
                            {group.manual && (
                              <Badge variant="outline" className="ml-2 border-amber-300 bg-amber-100 text-amber-800">
                                Manual
                              </Badge>
                            )}
                          </TableCell>
                          {isManagement && (
                            <TableCell className={HIDE_BELOW_SM} onClick={(e) => e.stopPropagation()}>
                              <Button
                                size="sm"
                                variant="ghost"
                                className="text-xs"
                                title={group.excluded || group.manual ? "Restaurar" : "Excluir"}
                                onClick={() => handleToggleExclude(group)}
                              >
                                {group.excluded || group.manual ? (
                                  <>
                                    <RotateCcw className="w-3.5 h-3.5" />
                                    Restaurar
                                  </>
                                ) : (
                                  <>
                                    <Ban className="w-3.5 h-3.5" />
                                    Excluir
                                  </>
                                )}
                              </Button>
                            </TableCell>
                          )}
                        </TableRow>
                        {isOpen && (
                          <TableRow key={`${group.invoice_id}-detail`}>
                            <TableCell colSpan={isManagement ? 9 : 8} className="bg-gray-50 p-0">
                              {/* Columns hidden at this width show here instead. */}
                              <div className="flex items-center justify-between gap-2 px-4 pt-3 text-xs text-gray-600 lg:hidden">
                                <p>
                                  {ZONE_LABELS[group.zone] ?? group.zone} · 
                                  <span className="sm:hidden">Pagada el {formatDay(group.paid_date)} · </span>
                                  {group.days_late > 0 ? `${group.days_late} días tarde` : "A tiempo"}
                                </p>
                                {isManagement && (
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    className="h-7 text-xs sm:hidden"
                                    onClick={() => handleToggleExclude(group)}
                                  >
                                    {group.excluded || group.manual ? (
                                      <><RotateCcw className="w-3.5 h-3.5" />Restaurar</>
                                    ) : (
                                      <><Ban className="w-3.5 h-3.5" />Excluir</>
                                    )}
                                  </Button>
                                )}
                              </div>
                              <Table>
                                <TableHeader>
                                  <TableRow className="hover:bg-transparent">
                                    <TableHead className="pl-4 lg:pl-14">Producto</TableHead>
                                    <TableHead className={cn("whitespace-nowrap", HIDE_BELOW_SM)}>Categoría</TableHead>
                                    <TableHead className={cn("text-right", HIDE_BELOW_LG)}>
                                      Cantidad
                                    </TableHead>
                                    <TableHead className={cn("text-right whitespace-nowrap", HIDE_BELOW_LG)}>
                                      Precio unit.
                                    </TableHead>
                                    <TableHead className={cn("text-right whitespace-nowrap", HIDE_BELOW_SM)}>
                                      Monto neto
                                    </TableHead>
                                    <TableHead className="text-right">Tasa</TableHead>
                                    <TableHead className="text-right lg:pr-8">
                                      Comisión
                                    </TableHead>
                                  </TableRow>
                                </TableHeader>
                                <TableBody>
                                  {group.lines.map((line, i) => (
                                    <TableRow
                                      key={`${line.invoice_id}-${line.producto_codigo}-${i}`}
                                      className="hover:bg-transparent"
                                    >
                                      <TableCell className="pl-4 lg:pl-14 min-w-40 sm:max-w-48 lg:max-w-64 sm:truncate">
                                        {line.producto_nombre}
                                        {line.cash_share != null && (
                                          <p className="text-xs text-gray-500">
                                            Comisión sobre el {Math.round(line.cash_share * 100)}% pagado en dinero (nota de crédito)
                                          </p>
                                        )}
                                      </TableCell>
                                      <TableCell className={HIDE_BELOW_SM}>
                                        {line.category && (
                                          <Badge
                                            variant="outline"
                                            className={cn("whitespace-nowrap", CATEGORY_BADGE[line.category])}
                                          >
                                            {CATEGORY_LABELS[line.category] ??
                                              line.category}
                                          </Badge>
                                        )}
                                      </TableCell>
                                      <TableCell className={cn("text-right num", HIDE_BELOW_LG)}>
                                        {line.quantity != null ? quantity(line.quantity) : "-"}
                                      </TableCell>
                                      <TableCell className={cn("text-right num", HIDE_BELOW_LG)}>
                                        {line.unit_amount != null
                                          ? formatMoney(line.unit_amount)
                                          : "-"}
                                      </TableCell>
                                      <TableCell className={cn("text-right num", HIDE_BELOW_SM)}>
                                        {formatMoney(line.net_amount)}
                                      </TableCell>
                                      <TableCell className="text-right num">
                                        {isManagement && line.movimiento_id != null && !group.excluded ? (
                                          <button
                                            onClick={() => openRateDialog(line)}
                                            title={
                                              line.auto_rate != null
                                                ? `Tasa cambiada por gerencia (automática ${(line.auto_rate * 100).toFixed(2)}%)${line.rate_note ? `: ${line.rate_note}` : ""}`
                                                : "Cambiar tasa"
                                            }
                                            className={cn(
                                              "rounded px-1.5 py-0.5 underline decoration-dotted underline-offset-4 hover:bg-gray-200",
                                              line.auto_rate != null && "bg-amber-100 text-amber-900",
                                            )}
                                          >
                                            {line.rate != null ? `${(line.rate * 100).toFixed(2)}%` : "-"}
                                          </button>
                                        ) : (
                                          <span className={cn(line.auto_rate != null && "rounded bg-amber-100 px-1.5 py-0.5 text-amber-900")}>
                                            {line.rate != null ? `${(line.rate * 100).toFixed(2)}%` : "-"}
                                          </span>
                                        )}
                                      </TableCell>
                                      <TableCell className="text-right num lg:pr-8">
                                        {formatMoney(line.commission)}
                                      </TableCell>
                                    </TableRow>
                                  ))}
                                </TableBody>
                              </Table>
                            </TableCell>
                          </TableRow>
                        )}
                      </Fragment>
                    );
                  })}
                  {invoiceGroups.length === 0 && <EmptyRow colSpan={isManagement ? 9 : 8}>Sin facturas que mostrar.</EmptyRow>}
                </TableBody>
              </Table>
            </div>
          </div>
        </div>
      )}

      <Dialog open={rateLine != null} onOpenChange={(open) => !open && setRateLine(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Cambiar tasa de comisión</DialogTitle>
          </DialogHeader>
          {rateLine && (
            <div className="flex flex-col gap-4">
              <div className="text-sm text-gray-700">
                <p className="font-medium">{rateLine.producto_nombre}</p>
                <p className="text-gray-500">
                  {rateLine.folio_display} · Monto neto {formatMoney(rateLine.net_amount)} · Tasa automática{" "}
                  {((rateLine.auto_rate ?? rateLine.rate ?? 0) * 100).toFixed(2)}%
                </p>
              </div>
              <div className="grid grid-cols-[8rem_1fr] gap-3">
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="line-rate">Tasa (%)</Label>
                  <Input
                    id="line-rate"
                    type="number"
                    step="0.25"
                    min="0"
                    max="20"
                    value={ratePercent}
                    onChange={(e) => setRatePercent(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleSaveRate()}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="line-rate-note">Nota</Label>
                  <Input
                    id="line-rate-note"
                    value={rateNote}
                    onChange={(e) => setRateNote(e.target.value)}
                    placeholder="Motivo del cambio"
                  />
                </div>
              </div>
              {rateError && <p className="text-sm text-red-600">{rateError}</p>}
              <div className="flex flex-wrap justify-end gap-2">
                {rateLine.auto_rate != null && (
                  <Button variant="outline" onClick={() => saveLineRate(null)} disabled={rateSaving}>
                    <RotateCcw className="w-4 h-4" />
                    Usar tasa automática
                  </Button>
                )}
                <Button onClick={handleSaveRate} disabled={rateSaving}>
                  {rateSaving ? "Guardando..." : "Guardar"}
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Agregar factura con monto manual</DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-4">
            <div className="flex items-end gap-2">
              <div className="flex-1 flex flex-col gap-1.5">
                <Label htmlFor="search-folio">Folio de factura</Label>
                <Input
                  id="search-folio"
                  value={searchFolio}
                  onChange={(e) => setSearchFolio(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                  placeholder="Ej. 20512"
                />
              </div>
              <Button onClick={handleSearch} disabled={searching}>
                {searching ? <Loader2 className="w-4 h-4 animate-spin" /> : "Buscar"}
              </Button>
            </div>

            {searchError && <p className="text-sm text-red-600">{searchError}</p>}

            {searchResults.length > 0 && (
              <div className="flex flex-col gap-1 max-h-48 overflow-y-auto rounded-md border">
                {searchResults.map((invoice) => (
                  <button
                    key={invoice.invoice_id}
                    onClick={() => handleSelectInvoice(invoice)}
                    className={cn(
                      "flex items-center justify-between px-3 py-2 text-left text-sm hover:bg-gray-50",
                      selectedInvoice?.invoice_id === invoice.invoice_id && "bg-slate-100",
                    )}
                  >
                    <span className="truncate">{invoice.cliente}</span>
                    <span className="ml-2 shrink-0 num text-gray-500">
                      {formatMoney(invoice.total)}
                    </span>
                  </button>
                ))}
              </div>
            )}

            {selectedInvoice && (
              <div className="flex flex-col gap-3 rounded-md border p-3">
                <p className="text-sm text-gray-700">
                  Factura {selectedInvoice.folio} - {selectedInvoice.cliente}
                </p>
                <div className="grid grid-cols-2 gap-3">
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="override-amount">Monto de comisión</Label>
                    <Input
                      id="override-amount"
                      type="number"
                      step="0.01"
                      value={overrideAmount}
                      onChange={(e) => setOverrideAmount(e.target.value)}
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="override-zone">Zona</Label>
                    <select
                      id="override-zone"
                      value={overrideZone}
                      onChange={(e) => setOverrideZone(e.target.value as Zone)}
                      className="h-10 rounded-md border border-input bg-background px-3 text-sm"
                    >
                      <option value="">Seleccionar...</option>
                      {COMMISSION_ZONES.map((zone) => (
                        <option key={zone} value={zone}>
                          {ZONE_LABELS[zone]}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="override-note">Nota</Label>
                  <Input
                    id="override-note"
                    value={overrideNote}
                    onChange={(e) => setOverrideNote(e.target.value)}
                    placeholder="Motivo del ajuste manual"
                  />
                </div>
                {overrideError && <p className="text-sm text-red-600">{overrideError}</p>}
                <Button onClick={handleSubmitAdd} disabled={overrideSubmitting}>
                  {overrideSubmitting ? "Guardando..." : "Guardar"}
                </Button>
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </main>
  );
}
