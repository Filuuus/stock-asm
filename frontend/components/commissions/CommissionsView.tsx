"use client";

import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Ban,
  ChevronDown,
  ChevronRight,
  Info,
  Loader2,
  Plus,
  RotateCcw,
  X,
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
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
import { cn } from "@/lib/utils";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/hooks/use-auth";
import { CommissionLine, CommissionsSummary, InvoiceSearchResult, Zone } from "@/types/commissions";

const ZONE_LABELS: Record<Zone, string> = {
  ZONA1: "Zona 1 (Juan Jose Franco)",
  ZONA2: "Zona 2 (Jesus Mendez)",
  OFICINA: "Oficina",
  SERVICIOS: "Servicios",
  PUNTOVENTA: "Punto de Venta",
};

const CATEGORY_LABELS: Record<string, string> = {
  R: "Refacciones",
  R_NW: "Refacciones (Tapetes y pernos)",
  R_CHEM: "Refacciones (Químicos)",
  R_FAN: "Refacciones (Ventiladores)",
  B: "Bionat",
  S: "Servicios",
  ZERO: "Sin comisión",
};

const CATEGORY_BADGE: Record<string, string> = {
  R: "bg-blue-100 text-blue-800 border-blue-200",
  R_NW: "bg-sky-100 text-sky-800 border-sky-200",
  R_CHEM: "bg-cyan-100 text-cyan-800 border-cyan-200",
  R_FAN: "bg-indigo-100 text-indigo-800 border-indigo-200",
  B: "bg-green-100 text-green-800 border-green-200",
  S: "bg-purple-100 text-purple-800 border-purple-200",
  ZERO: "bg-gray-100 text-gray-600 border-gray-200",
};

interface InvoiceGroup {
  invoice_id: number;
  folio: number;
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

function currency(value: number) {
  return value.toLocaleString("es-MX", {
    style: "currency",
    currency: "MXN",
    maximumFractionDigits: 0,
  });
}

function currencyPrecise(value: number) {
  return value.toLocaleString("es-MX", {
    style: "currency",
    currency: "MXN",
    maximumFractionDigits: 2,
  });
}

function quantity(value: number) {
  return value.toLocaleString("es-MX", { maximumFractionDigits: 2 });
}

function currentMonth() {
  return new Date().toISOString().slice(0, 7);
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
  return [...groups.values()].sort((a, b) => b.commission_total - a.commission_total);
}

export default function CommissionsView() {
  const { loading: authLoading, isWorker, isManagement } = useAuth();
  const [month, setMonth] = useState(currentMonth());
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

  const requestIdRef = useRef(0);

  const fetchSummary = async (targetMonth: string) => {
    // The native <input type="month"> can fire onChange with an incomplete
    // value while being typed into (e.g. "2026-0" before the second digit
    // lands) - fetching on that crashes the backend's date parser and, since
    // nothing here previously guarded against overlapping requests, could
    // leave the spinner stuck if an older request resolved after a newer
    // one. Found live during a demo (2026-09-17): a 500 from a malformed
    // date, likely combined with an out-of-order response.
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
        `${g.cliente} ${g.folio}`.toLowerCase().includes(q) ||
        g.lines.some((l) =>
          `${l.producto_nombre} ${l.producto_codigo ?? ""}`.toLowerCase().includes(q),
        ),
    );
  }, [data, filter, selectedZone]);

  if (!authLoading && !isWorker) {
    return (
      <main className="max-w-7xl mx-auto w-full p-6">
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
    <main className="max-w-7xl mx-auto w-full p-6 flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold text-gray-900">
          Comisiones por Zona
        </h1>
        <p className="text-sm text-gray-500">
          Cálculo automático a partir de facturas pagadas en su totalidad -
          borrador para revisión, no es el pago oficial.
        </p>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-600">Mes</label>
          <Input
            type="month"
            value={month}
            onChange={(e) => handleMonthChange(e.target.value)}
            className="w-40"
          />
        </div>
        {(loading || authLoading) && (
          <Loader2 className="w-4 h-4 mb-2 animate-spin text-gray-400" />
        )}
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {data && !error && (
        <>
          <Card>
            <CardHeader>
              <CardDescription>
                Total de comisiones, {data.date_from} a {data.date_to}
              </CardDescription>
              <CardTitle className="text-3xl">
                {currency(totalCommission)}
              </CardTitle>
            </CardHeader>
          </Card>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
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
                  <CardTitle className="text-xl">
                    {currency(data.zone_totals[zone] ?? 0)}
                  </CardTitle>
                </CardHeader>
              </Card>
            ))}
          </div>

          {data.unresolved_payment_date.count > 0 && (
            <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
              <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" />
              <div>
                <p className="font-medium">
                  {data.unresolved_payment_date.count} facturas pagadas sin
                  fecha de pago rastreable ({currency(data.unresolved_payment_date.total_amount)})
                </p>
                <p className="text-amber-700">
                  {data.unresolved_payment_date.note}
                </p>
              </div>
            </div>
          )}

          {data.credit_noted.count > 0 && (
            <div className="flex items-start gap-3 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
              <Info className="w-5 h-5 shrink-0 mt-0.5" />
              <div>
                <p className="font-medium">
                  {data.credit_noted.count} facturas liquidadas por nota de
                  crédito ({currency(data.credit_noted.total_amount)})
                </p>
                <p className="text-slate-600">{data.credit_noted.note}</p>
              </div>
            </div>
          )}

          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-semibold text-gray-900">
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
                  <Button size="sm" variant="outline" onClick={openAddDialog}>
                    <Plus className="w-4 h-4" />
                    Agregar factura
                  </Button>
                )}
                <Input
                  placeholder="Buscar cliente, producto o folio..."
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                  className="w-72"
                />
              </div>
            </div>

            <div className="rounded-lg border bg-white">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-8" />
                    <TableHead>Folio</TableHead>
                    <TableHead>Cliente</TableHead>
                    <TableHead>Zona</TableHead>
                    <TableHead>Fecha de pago</TableHead>
                    <TableHead className="text-right">Días tarde</TableHead>
                    <TableHead className="text-right">Items</TableHead>
                    <TableHead className="text-right">Comisión</TableHead>
                    {isManagement && <TableHead className="w-28" />}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {invoiceGroups.map((group) => {
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
                          <TableCell>
                            {isOpen ? (
                              <ChevronDown className="w-4 h-4 text-gray-400" />
                            ) : (
                              <ChevronRight className="w-4 h-4 text-gray-400" />
                            )}
                          </TableCell>
                          <TableCell className={cn("font-mono text-xs", group.excluded && "line-through")}>
                            {group.folio}
                          </TableCell>
                          <TableCell className={cn("max-w-56 truncate", group.excluded && "line-through")}>
                            {group.cliente}
                          </TableCell>
                          <TableCell className="text-xs text-gray-600">
                            {ZONE_LABELS[group.zone] ?? group.zone}
                          </TableCell>
                          <TableCell className="text-xs text-gray-600">
                            {group.paid_date?.slice(0, 10)}
                          </TableCell>
                          <TableCell className="text-right font-mono text-xs">
                            {group.days_late > 0 ? group.days_late : "-"}
                          </TableCell>
                          <TableCell className="text-right text-xs text-gray-600">
                            {group.lines.length}
                          </TableCell>
                          <TableCell className="text-right font-mono font-medium">
                            {currency(group.commission_total)}
                            {group.manual && (
                              <Badge variant="outline" className="ml-2 border-amber-300 bg-amber-100 text-amber-800">
                                Manual
                              </Badge>
                            )}
                          </TableCell>
                          {isManagement && (
                            <TableCell onClick={(e) => e.stopPropagation()}>
                              <Button
                                size="sm"
                                variant="ghost"
                                className="text-xs"
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
                              <Table>
                                <TableHeader>
                                  <TableRow className="hover:bg-transparent">
                                    <TableHead className="pl-14">Producto</TableHead>
                                    <TableHead>Categoría</TableHead>
                                    <TableHead className="text-right">
                                      Cantidad
                                    </TableHead>
                                    <TableHead className="text-right">
                                      Precio unit.
                                    </TableHead>
                                    <TableHead className="text-right">
                                      Monto neto
                                    </TableHead>
                                    <TableHead className="text-right">Tasa</TableHead>
                                    <TableHead className="text-right pr-8">
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
                                      <TableCell className="pl-14 max-w-64 truncate text-sm">
                                        {line.producto_nombre}
                                      </TableCell>
                                      <TableCell>
                                        {line.category && (
                                          <Badge
                                            variant="outline"
                                            className={CATEGORY_BADGE[line.category]}
                                          >
                                            {CATEGORY_LABELS[line.category] ??
                                              line.category}
                                          </Badge>
                                        )}
                                      </TableCell>
                                      <TableCell className="text-right font-mono text-xs">
                                        {line.quantity != null ? quantity(line.quantity) : "-"}
                                      </TableCell>
                                      <TableCell className="text-right font-mono text-xs">
                                        {line.unit_amount != null
                                          ? currencyPrecise(line.unit_amount)
                                          : "-"}
                                      </TableCell>
                                      <TableCell className="text-right font-mono text-xs">
                                        {currency(line.net_amount)}
                                      </TableCell>
                                      <TableCell className="text-right font-mono text-xs">
                                        {line.rate != null ? `${(line.rate * 100).toFixed(2)}%` : "-"}
                                      </TableCell>
                                      <TableCell className="text-right font-mono text-sm pr-8">
                                        {currency(line.commission)}
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
                  {invoiceGroups.length === 0 && (
                    <TableRow>
                      <TableCell
                        colSpan={isManagement ? 9 : 8}
                        className="text-center text-sm text-gray-500 py-8"
                      >
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
                    <span className="ml-2 shrink-0 font-mono text-xs text-gray-500">
                      {currency(invoice.total)}
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
                      {(Object.keys(ZONE_LABELS) as Zone[]).map((zone) => (
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
