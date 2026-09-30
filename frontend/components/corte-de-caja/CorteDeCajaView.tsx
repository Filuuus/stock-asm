"use client";

import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { addDays } from "date-fns";
import {
  Check,
  ChevronLeft,
  ChevronRight,
  Loader2,
  Pencil,
  X,
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import DiferenciasFechaView from "@/components/corte-de-caja/DiferenciasFechaView";
import InvoiceLink from "@/components/facturas/InvoiceLink";
import ClientLink from "@/components/facturas/ClientLink";
import { DateRangeControl } from "@/components/date-controls";
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
import { HIDE_BELOW_LG, HIDE_BELOW_SM } from "@/components/sortable-table";
import { cn, formatMoney, plural } from "@/lib/utils";
import { Notice, NoticeList } from "@/components/notice";
import { dateToISO, formatDay, isoToDate, todayISO } from "@/lib/dates";
import { ZONE_LABELS, ZONE_ORDER } from "@/lib/zones";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/hooks/use-auth";
import { Zone } from "@/types/commissions";
import { CorteDeCajaRow, CorteDeCajaSummary, PaymentMethod } from "@/types/corte-de-caja";

const CATEGORY_LABELS: Record<string, string> = {
  R: "Refacciones",
  R_NW: "Refacciones (Tapetes y pernos)",
  R_CHEM: "Refacciones (Químicos)",
  R_FAN: "Refacciones (Ventiladores)",
  B: "Bionat",
  B_MIPRO: "Bionat (Mipro)",
  B_BOVI: "Bionat (Bovifit)",
  S: "Servicios",
};

const METHOD_LABELS: Record<PaymentMethod, string> = {
  EFECTIVO: "Efectivo",
  TERMINAL: "Terminal",
  CHEQUE: "Cheque",
  TRANSFERENCIA: "Transferencia",
};


export default function CorteDeCajaView() {
  const { loading: authLoading, isAccounting, isManagement } = useAuth();
  const canUse = isAccounting || isManagement;

  const [dateFrom, setDateFrom] = useState(todayISO());
  const [dateTo, setDateTo] = useState(todayISO());
  const [data, setData] = useState<CorteDeCajaSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [selectedZone, setSelectedZone] = useState<Zone | null>(null);

  const [editingRow, setEditingRow] = useState<CorteDeCajaRow | null>(null);
  const [editNote, setEditNote] = useState("");
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [confirmingBulk, setConfirmingBulk] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());
  const [view, setView] = useState<"corte" | "diferencias">("corte");

  const requestIdRef = useRef(0);

  const fetchSummary = async (from: string, to: string) => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(from) || !/^\d{4}-\d{2}-\d{2}$/.test(to)) return;

    const requestId = ++requestIdRef.current;
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch(
        `/api/corte-de-caja/summary/?date_from=${from}&date_to=${to}`,
        { cache: "no-store" },
      );
      if (!res.ok) throw new Error(`El servidor respondió ${res.status}`);
      const json = await res.json();
      if (requestId !== requestIdRef.current) return;
      setData(json);
    } catch (err) {
      if (requestId !== requestIdRef.current) return;
      setError(err instanceof Error ? err.message : "No se pudo cargar la información");
    } finally {
      if (requestId === requestIdRef.current) setLoading(false);
    }
  };

  useEffect(() => {
    if (!canUse) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchSummary(dateFrom, dateTo);
    // Intentionally run once auth resolves - handleDateChange covers refetches.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canUse]);

  const handleDateChange = (from: string, to: string) => {
    setDateFrom(from);
    setDateTo(to);
    fetchSummary(from, to);
  };

  // Shifts the whole [dateFrom, dateTo] window by one day, preserving its
  // span - so this also works sensibly when a multi-day range is selected,
  // not just a single day.
  const handleShiftDays = (delta: number) => {
    const from = dateToISO(addDays(isoToDate(dateFrom), delta));
    const to = dateToISO(addDays(isoToDate(dateTo), delta));
    handleDateChange(from, to);
  };

  const handleZoneClick = (zone: Zone) => {
    setSelectedZone((prev) => (prev === zone ? null : zone));
  };

  const patchAdjustment = async (row: CorteDeCajaRow, body: Record<string, unknown>) => {
    const res = await apiFetch("/api/corte-de-caja/adjustments/", {
      method: "POST",
      body: JSON.stringify({ invoice_id: row.invoice_id, event_date: row.event_date, ...body }),
    });
    const json = await res.json();
    if (!res.ok) throw new Error(json.error ?? "No se pudo guardar el ajuste.");
    return json;
  };

  const handleMethodChange = async (row: CorteDeCajaRow, method: string) => {
    try {
      await patchAdjustment(row, { payment_method: method, bank_code: row.bank_code });
      fetchSummary(dateFrom, dateTo);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo actualizar la forma de pago.");
    }
  };

  const handleConfirmHighConfidence = async () => {
    setConfirmingBulk(true);
    try {
      const res = await apiFetch("/api/corte-de-caja/confirm-suggestions/", {
        method: "POST",
        body: JSON.stringify({ date_from: dateFrom, date_to: dateTo, tiers: ["alta"] }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error ?? "No se pudieron confirmar las sugerencias.");
      fetchSummary(dateFrom, dateTo);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudieron confirmar las sugerencias.");
    } finally {
      setConfirmingBulk(false);
    }
  };

  const handleToggleReviewed = async (row: CorteDeCajaRow) => {
    try {
      await patchAdjustment(row, { reviewed: !row.reviewed });
      fetchSummary(dateFrom, dateTo);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo actualizar la factura.");
    }
  };

  const rowKey = (row: CorteDeCajaRow) => `${row.invoice_id}-${row.event_date}`;

  const toggleExpanded = (row: CorteDeCajaRow) => {
    const key = rowKey(row);
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const openEditDialog = (row: CorteDeCajaRow) => {
    setEditingRow(row);
    setEditNote(row.note);
    setEditError(null);
  };

  const handleSubmitEdit = async () => {
    if (!editingRow) return;
    setEditSubmitting(true);
    setEditError(null);
    try {
      await patchAdjustment(editingRow, { note: editNote });
      setEditingRow(null);
      fetchSummary(dateFrom, dateTo);
    } catch (err) {
      setEditError(err instanceof Error ? err.message : "No se pudo guardar el ajuste.");
    } finally {
      setEditSubmitting(false);
    }
  };

  const rows = useMemo(() => {
    if (!data) return [];
    let filtered = data.rows;
    if (selectedZone) filtered = filtered.filter((r) => r.zone === selectedZone);
    const q = filter.trim().toLowerCase();
    if (!q) return filtered;
    return filtered.filter((r) => `${r.cliente} ${r.folio_display}`.toLowerCase().includes(q));
  }, [data, filter, selectedZone]);

  // One block per zone, like the accountant's sheet and the .xlsx export -
  // a header row instead of repeating the zone/salesperson name on every
  // payment, sorted the same way (cliente, then date, then folio).
  const zoneGroups = useMemo(() => {
    const byZone = new Map<Zone, CorteDeCajaRow[]>();
    for (const row of rows) {
      const list = byZone.get(row.zone) ?? [];
      list.push(row);
      byZone.set(row.zone, list);
    }
    const order = (zone: Zone) => {
      const i = ZONE_ORDER.indexOf(zone);
      return i === -1 ? ZONE_ORDER.length : i;
    };
    return [...byZone.entries()]
      .sort(([a], [b]) => order(a) - order(b))
      .map(([zone, zoneRows]) => ({
        zone,
        rows: [...zoneRows].sort(
          (a, b) =>
            a.cliente.localeCompare(b.cliente) ||
            a.event_date.localeCompare(b.event_date) ||
            a.folio_display.localeCompare(b.folio_display),
        ),
        subtotal: zoneRows.reduce((sum, r) => sum + r.amount, 0),
      }));
  }, [rows]);

  if (!authLoading && !canUse) {
    return (
      <main className="max-w-7xl mx-auto w-full p-4 sm:p-6">
        <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-gray-300 bg-white py-16 text-center">
          <p className="text-sm font-medium text-gray-700">
            {authLoading ? "" : "No tiene permiso para ver el Corte de Caja."}
          </p>
          <a href="/login" className="text-sm font-medium text-slate-900 underline">
            Iniciar sesión
          </a>
        </div>
      </main>
    );
  }

  const viewTabs = (
    <Tabs value={view} onValueChange={(v) => setView(v as "corte" | "diferencias")}>
      <TabsList>
        <TabsTrigger value="corte">Corte diario</TabsTrigger>
        <TabsTrigger value="diferencias">Discrepancias</TabsTrigger>
      </TabsList>
    </Tabs>
  );

  // Title, then the description of the tab being shown, then the tabs -
  // the same order on every page.
  const header = (
    <div className="flex flex-col gap-1">
      <h1 className="text-2xl font-bold text-gray-900">Corte de Caja</h1>
      <p className="text-sm text-gray-500">
        {view === "diferencias"
          ? "Cada pago de cliente en Contpaqi Comercial junto a su póliza en Contabilidad. " +
            "Los pagos registrados en un mes en Comercial y en otro en Contabilidad se declaran en " +
            "periodos distintos; también se marcan las pólizas con otro importe o que citan un folio " +
            "equivocado. Corríjalos en Contpaqi. Un pago aparece en el mes de cualquiera de sus dos fechas."
          : "Cobranza diaria calculada automáticamente desde el ERP - un renglón por cada pago " +
            "identificado (incluye abonos parciales). La forma de pago se sugiere según el historial " +
            "confirmado de cada cliente - confirme las de confianza alta con un clic y elija las demás."}
      </p>
    </div>
  );

  if (view === "diferencias") {
    return (
      <main className="max-w-7xl mx-auto w-full p-4 sm:p-6 flex flex-col gap-6">
        {header}
        {viewTabs}
        <DiferenciasFechaView />
      </main>
    );
  }

  // Payment-method picker: in its own column from sm up, inside the
  // expanded row on phones.
  const methodPicker = (row: CorteDeCajaRow) => (
    <div className="flex items-center gap-1">
      <select
        value={row.payment_method}
        onChange={(e) => handleMethodChange(row, e.target.value)}
        className={cn(
          "h-8 rounded-md border px-2 text-xs",
          row.payment_method_confirmed
            ? "border-input bg-background"
            : row.suggestion_confidence === "alta"
              ? "border-emerald-300 bg-emerald-50"
              : row.suggestion_confidence === "media"
                ? "border-sky-300 bg-sky-50"
                : "border-amber-400 bg-amber-50",
        )}
        title={
          row.payment_method && !row.payment_method_confirmed
            ? `Sin confirmar - ${row.suggestion_reason}`
            : undefined
        }
      >
        <option value="">Sin clasificar</option>
        {(Object.keys(METHOD_LABELS) as PaymentMethod[]).map((m) => (
          <option key={m} value={m}>
            {METHOD_LABELS[m]}
          </option>
        ))}
      </select>
      {row.payment_method && !row.payment_method_confirmed && (
        <span
          className={cn(
            "shrink-0 whitespace-nowrap text-[10px] font-medium uppercase tracking-wide",
            row.suggestion_confidence === "alta"
              ? "text-emerald-700"
              : row.suggestion_confidence === "media"
                ? "text-sky-700"
                : "text-amber-700",
          )}
          title={row.suggestion_reason}
        >
          {row.suggestion_confidence === "baja" ? "elegir" : row.suggestion_confidence}
        </span>
      )}
      {row.payment_method && !row.payment_method_confirmed && (
        <Button
          size="sm"
          variant="ghost"
          className="px-1.5 h-8"
          title="Confirmar sugerencia"
          onClick={() => handleMethodChange(row, row.payment_method)}
        >
          <Check className="w-3.5 h-3.5 text-sky-600" />
        </Button>
      )}
    </div>
  );

  return (
    <main className="max-w-7xl mx-auto w-full p-4 sm:p-6 flex flex-col gap-6">
      {header}
      {viewTabs}

      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="icon"
          variant="outline"
          onClick={() => handleShiftDays(-1)}
          title="Día anterior"
        >
          <ChevronLeft className="w-4 h-4" />
        </Button>
        <DateRangeControl dateFrom={dateFrom} dateTo={dateTo} onChange={handleDateChange} />
        <Button
          size="icon"
          variant="outline"
          onClick={() => handleShiftDays(1)}
          title="Día siguiente"
        >
          <ChevronRight className="w-4 h-4" />
        </Button>
        {(loading || authLoading) && (
          <Loader2 className="w-4 h-4 animate-spin text-gray-400" />
        )}
      </div>

      {error && <Notice tone="error" summary={error} />}

      {data && !error && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-5">
            <Card className="col-span-2 md:col-span-4 lg:col-span-1 border-slate-900">
              <CardHeader className="p-4">
                <CardDescription>TOTAL CORTE</CardDescription>
                <CardTitle className="text-xl">{formatMoney(data.cash_drawer_total)}</CardTitle>
                <p className="text-xs text-gray-400">efectivo + terminal + cheque</p>
              </CardHeader>
            </Card>
            {(["EFECTIVO", "TERMINAL", "CHEQUE", "TRANSFERENCIA"] as PaymentMethod[]).map((method) => (
              <Card key={method}>
                <CardHeader className="p-4">
                  <CardDescription>{METHOD_LABELS[method]}</CardDescription>
                  <CardTitle className="text-lg sm:text-xl">{formatMoney(data.method_totals[method] ?? 0)}</CardTitle>
                </CardHeader>
              </Card>
            ))}
          </div>

          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5 [&>*:last-child:nth-child(odd)]:col-span-2 lg:[&>*:last-child:nth-child(odd)]:col-span-1">
            {(Object.keys(ZONE_LABELS) as Zone[]).map((zone) => (
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
                  <CardTitle className="text-lg sm:text-xl">{formatMoney(data.zone_totals[zone] ?? 0)}</CardTitle>
                </CardHeader>
              </Card>
            ))}
          </div>

          {data.unclassified.count > 0 && (
            <Notice
              tone="warning"
              title={`${plural(data.unclassified.count, "pago", "pagos")} sin forma de pago (${formatMoney(data.unclassified.total_amount)})`}
              summary="Clasifíquelos para que entren en los totales."
            >
              <p>{data.unclassified.note}</p>
            </Notice>
          )}

          {data.unconfirmed.count > 0 && (
            <Notice
              tone="info"
              title={`${plural(data.unconfirmed.count, "pago", "pagos")} con forma de pago sin confirmar (${formatMoney(data.unconfirmed.total_amount)})`}
              summary={
                `${data.suggestions.alta.count} de confianza alta, ${data.suggestions.media.count} media, ` +
                `${data.suggestions.baja.count} por elegir (sin historial suficiente).`
              }
              action={
                data.suggestions.alta.count > 0 && (
                  <Button
                    size="sm"
                    onClick={handleConfirmHighConfidence}
                    disabled={confirmingBulk}
                    title="Confirma solo las sugerencias de confianza alta de este rango de fechas"
                  >
                    {confirmingBulk ? (
                      <Loader2 className="w-4 h-4 animate-spin mr-1" />
                    ) : (
                      <Check className="w-4 h-4 mr-1" />
                    )}
                    Confirmar las {data.suggestions.alta.count} de confianza alta
                  </Button>
                )
              }
            >
              <p>{data.unconfirmed.note}</p>
            </Notice>
          )}

          {data.sin_poliza.count > 0 && (
            <Notice
              tone="warning"
              title={`${plural(data.sin_poliza.count, "pago", "pagos")} en Comercial sin póliza en Contabilidad (${formatMoney(data.sin_poliza.total_amount)})`}
              summary="No se incluyen en el corte hasta que se registre la póliza en Contpaqi."
            >
              <p>{data.sin_poliza.note}</p>
              <NoticeList
                rows={data.sin_poliza.rows}
                rowKey={(r) => `${r.invoice_id}-${r.comercial_date}-${r.pago}`}
                columns={[
                  { label: "Factura", cell: (r) => <span className="num"><InvoiceLink invoiceId={r.invoice_id} label={r.folio_display} /></span> },
                  { label: "Cliente", cell: (r) => <ClientLink clientId={r.client_id} label={r.cliente} /> },
                  { label: "Pago en Comercial", cell: (r) => `${formatDay(r.comercial_date)} · ${r.pago}` },
                  {
                    label: "Fecha factura",
                    cell: (r) =>
                      r.invoice_date > r.comercial_date ? (
                        <span
                          className="font-medium text-red-700"
                          title="El pago es anterior a la factura: revisar en Comercial a qué factura se aplicó"
                        >
                          {formatDay(r.invoice_date)}
                        </span>
                      ) : (
                        formatDay(r.invoice_date)
                      ),
                  },
                  { label: "Total factura", cell: (r) => <span className="num">{formatMoney(r.invoice_total)}</span>, align: "right" },
                  { label: "Monto del pago", cell: (r) => <span className="num">{formatMoney(r.amount)}</span>, align: "right" },
                ]}
              />
            </Notice>
          )}

          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-semibold text-gray-900 whitespace-nowrap">Pagos ({rows.length})</h2>
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
              <Input
                placeholder="Buscar cliente o folio..."
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                className="w-full sm:w-72"
              />
            </div>

            <div className="rounded-lg border bg-white overflow-x-auto">
              {/* Tighter cell padding below desktop so the key columns fit. */}
              <Table className="[&_td]:px-2 [&_th]:px-2 lg:[&_td]:px-3 lg:[&_th]:px-3">
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-8" />
                    <TableHead className="w-8" />
                    <TableHead className={cn("whitespace-nowrap", HIDE_BELOW_SM)}>Fecha</TableHead>
                    <TableHead className="whitespace-nowrap">Folio</TableHead>
                    <TableHead className="whitespace-nowrap">Cliente</TableHead>
                    <TableHead className="whitespace-nowrap text-right">Monto</TableHead>
                    <TableHead className={cn("whitespace-nowrap", HIDE_BELOW_LG)}>Tipo</TableHead>
                    <TableHead className={cn("whitespace-nowrap", HIDE_BELOW_SM)}>Forma de pago</TableHead>
                    <TableHead className={cn("whitespace-nowrap", HIDE_BELOW_LG)}>Nota</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {zoneGroups.map(({ zone, rows: groupRows, subtotal }) => (
                    <Fragment key={zone}>
                      <TableRow className="bg-slate-50 hover:bg-slate-50">
                        <TableCell colSpan={9} className="py-2">
                          <div className="flex items-center justify-between">
                            <span className="text-sm font-semibold text-gray-800">
                              {ZONE_LABELS[zone] ?? zone}
                              <span className="ml-2 text-xs font-normal text-gray-500">
                                ({groupRows.length})
                              </span>
                            </span>
                            <span className="num font-semibold text-gray-800">
                              {formatMoney(subtotal)}
                            </span>
                          </div>
                        </TableCell>
                      </TableRow>
                      {groupRows.map((row) => {
                        const expanded = expandedRows.has(rowKey(row));
                        return (
                          <Fragment key={rowKey(row)}>
                            <TableRow className={cn(row.excluded && "opacity-50")}>
                              <TableCell>
                                <button
                                  onClick={() => toggleExpanded(row)}
                                  className="flex items-center justify-center rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
                                  title={expanded ? "Ocultar detalle" : "Ver detalle"}
                                >
                                  <ChevronRight
                                    className={cn("w-3.5 h-3.5 transition-transform", expanded && "rotate-90")}
                                  />
                                </button>
                              </TableCell>
                              <TableCell>
                                <Checkbox
                                  checked={row.reviewed}
                                  onCheckedChange={() => handleToggleReviewed(row)}
                                  title={row.reviewed ? `Revisado por ${row.reviewed_by ?? "?"}` : "Marcar como revisado"}
                                />
                              </TableCell>
                              <TableCell className={cn("text-gray-600 whitespace-nowrap", HIDE_BELOW_SM)}>{formatDay(row.event_date)}</TableCell>
                              <TableCell
                                className={cn("num", row.excluded && "line-through")}
                              >
                                <InvoiceLink invoiceId={row.invoice_id} label={row.folio_display} />
                              </TableCell>
                              <TableCell className={cn("max-w-[6.5rem] sm:max-w-36 lg:max-w-48 truncate", row.excluded && "line-through")}>
                                <ClientLink clientId={row.client_id} label={row.cliente} />
                              </TableCell>
                              <TableCell className="text-right num">
                                {formatMoney(row.amount)}
                              </TableCell>
                              <TableCell className={cn("whitespace-nowrap", HIDE_BELOW_LG)}>
                                {row.abono ? (
                                  <Badge variant="outline" className="bg-blue-50 text-blue-700 border-blue-200">
                                    Abono
                                  </Badge>
                                ) : (
                                  <Badge variant="outline" className="bg-green-50 text-green-700 border-green-200">
                                    Completo
                                  </Badge>
                                )}
                              </TableCell>
                              <TableCell className={HIDE_BELOW_SM} onClick={(e) => e.stopPropagation()}>
                                {methodPicker(row)}
                              </TableCell>
                              <TableCell className={HIDE_BELOW_LG} onClick={(e) => e.stopPropagation()}>
                                <div className="flex items-center gap-1">
                                  <span
                                    className="max-w-32 truncate text-gray-600"
                                    title={row.note || undefined}
                                  >
                                    {row.note || "-"}
                                  </span>
                                  <Button size="sm" variant="ghost" className="px-1.5 h-7" onClick={() => openEditDialog(row)}>
                                    <Pencil className="w-3.5 h-3.5" />
                                  </Button>
                                </div>
                              </TableCell>
                            </TableRow>
                            {expanded && (
                              <TableRow className="bg-slate-50/60 hover:bg-slate-50/60">
                                <TableCell />
                                <TableCell colSpan={8} className="py-3">
                                  <div className="grid grid-cols-2 gap-x-8 gap-y-2 text-xs sm:grid-cols-3">
                                    {/* Columns hidden at this width show here instead. */}
                                    <div className="col-span-2 sm:hidden">
                                      <p className="mb-1 text-gray-400">Forma de pago</p>
                                      {methodPicker(row)}
                                    </div>
                                    <div className="sm:hidden">
                                      <p className="text-gray-400">Fecha</p>
                                      <p className="text-gray-700">{formatDay(row.event_date)}</p>
                                    </div>
                                    <div className="lg:hidden">
                                      <p className="text-gray-400">Tipo</p>
                                      <p className="text-gray-700">{row.abono ? "Abono" : "Completo"}</p>
                                    </div>
                                    <div className="lg:hidden">
                                      <p className="text-gray-400">Nota</p>
                                      <button
                                        onClick={() => openEditDialog(row)}
                                        className="flex items-center gap-1 text-left text-gray-700 hover:text-gray-900"
                                      >
                                        {row.note || "-"}
                                        <Pencil className="w-3 h-3 shrink-0 text-gray-400" />
                                      </button>
                                    </div>
                                    <div>
                                      <p className="text-gray-400">Categoría</p>
                                      <p className="text-gray-700">
                                        {row.category ? (CATEGORY_LABELS[row.category] ?? row.category) : "-"}
                                      </p>
                                    </div>
                                    <div>
                                      <p className="text-gray-400">Banco</p>
                                      <p className="text-gray-700">{row.bank ?? "No identificado"}</p>
                                    </div>
                                    <div>
                                      <p className="text-gray-400">Cuenta</p>
                                      <p className="text-gray-700">{row.cuenta ?? "-"}</p>
                                    </div>
                                  </div>
                                </TableCell>
                              </TableRow>
                            )}
                          </Fragment>
                        );
                      })}
                    </Fragment>
                  ))}
                  {rows.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={9} className="text-center text-sm text-gray-500 py-8">
                        Sin resultados para este período.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>
          </div>
        </>
      )}

      <Dialog open={editingRow !== null} onOpenChange={(open) => !open && setEditingRow(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>
              Nota - factura {editingRow?.folio_display} ({formatDay(editingRow?.event_date)}) - {editingRow?.cliente}
            </DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="edit-note">Observaciones</Label>
              <Textarea id="edit-note" value={editNote} onChange={(e) => setEditNote(e.target.value)} rows={3} />
            </div>
            {editError && <p className="text-sm text-red-600">{editError}</p>}
            <Button onClick={handleSubmitEdit} disabled={editSubmitting}>
              {editSubmitting ? "Guardando..." : "Guardar"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </main>
  );
}
