"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { RefreshCw, Scale, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { EmptyRow, HIDE_BELOW_MD, HIDE_BELOW_SM, SortableHead, useSort } from "@/components/sortable-table";
import { MonthControl } from "@/components/date-controls";
import { CATEGORY_LABELS } from "@/components/catalog/CatalogFilters";
import { formatMonth, isoToDate, monthToISO } from "@/lib/dates";
import { zoneLabel, ZONE_ORDER } from "@/lib/zones";
import { cn, formatMoney } from "@/lib/utils";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/hooks/use-auth";
import type { Zone } from "@/types/commissions";

// [month "YYYY-MM", zone, client id, product id (null = credit note never applied), units, net, cost, kg]
type Fact = [string, string, number, number | null, number, number, number, number];
type WeightSource = "manual" | "nombre" | "GEA" | "unidad" | "estimado" | "servicio";

interface Product {
  code: string;
  name: string;
  brand: string;
  category: string;
  kg: number; // per sale unit
  source: WeightSource;
}

interface Profitability {
  facts: Fact[];
  excluded: number[]; // product ids left out altogether, with their returns and credit notes
  products: Record<string, Product>;
  clients: Record<string, string>;
}

type Dim = "zone" | "category" | "brand" | "product" | "client" | "month";
type Filters = Partial<Record<Exclude<Dim, "month">, string>>;

const DIMS: { key: Dim; label: string; one: string }[] = [
  { key: "zone", label: "Zona", one: "esa zona" },
  { key: "category", label: "Línea", one: "esa línea" },
  { key: "brand", label: "Marca", one: "esa marca" },
  { key: "product", label: "Producto", one: "ese producto" },
  { key: "client", label: "Cliente", one: "ese cliente" },
  { key: "month", label: "Mes", one: "ese mes" },
];
const NO_PRODUCT = "Sin producto";
const SOURCE_LABELS: Record<WeightSource, string> = {
  manual: "Capturado",
  nombre: "Del nombre",
  GEA: "Catálogo GEA",
  unidad: "Unidad del ERP",
  estimado: "Estimado",
  servicio: "Servicio",
};

function without<T extends object>(obj: T, key: keyof T): T {
  const copy = { ...obj };
  delete copy[key];
  return copy;
}

function lastCompleteMonth() {
  const d = new Date();
  return monthToISO(new Date(d.getFullYear(), d.getMonth() - 1, 1));
}

function shiftMonth(month: string, delta: number) {
  const d = isoToDate(month);
  return monthToISO(new Date(d.getFullYear(), d.getMonth() + delta, 1));
}

function percent(value: number) {
  return `${(value * 100).toLocaleString("es-MX", { maximumFractionDigits: 1 })}%`;
}

function tonnes(kg: number) {
  return `${(kg / 1000).toLocaleString("es-MX", { maximumFractionDigits: 1 })} t`;
}

interface Group {
  key: string;
  label: string;
  net: number;
  cost: number;
  kg: number;
}

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardHeader className="p-3 sm:p-4 space-y-1">
        <CardDescription className="text-xs sm:text-sm">{label}</CardDescription>
        <CardTitle className="text-base sm:text-xl">{value}</CardTitle>
      </CardHeader>
    </Card>
  );
}

export default function ProfitabilityView() {
  const { loading: authLoading, isManagement } = useAuth();
  const [to, setTo] = useState(lastCompleteMonth);
  const [from, setFrom] = useState(() => shiftMonth(lastCompleteMonth(), -11));
  const [data, setData] = useState<Profitability | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  const forceRefresh = useRef(false);
  const [filters, setFilters] = useState<Filters>({});
  const [groupBy, setGroupBy] = useState<Dim>("zone");
  const [weightsOpen, setWeightsOpen] = useState(false);
  const [excludedOpen, setExcludedOpen] = useState(false);
  const [excludeError, setExcludeError] = useState<string | null>(null);

  const setExcluded = async (productId: string, excluded: boolean) => {
    setExcludeError(null);
    const res = await apiFetch("/api/profitability/exclusions/", {
      method: "POST",
      body: JSON.stringify({ product_id: Number(productId), excluded }),
    });
    if (!res.ok) {
      setExcludeError("No se pudo guardar el cambio.");
      return;
    }
    if (excluded) setFilters((f) => (f.product === productId ? without(f, "product") : f));
    setReload((n) => n + 1);
  };

  useEffect(() => {
    if (!isManagement) return;
    const refresh = forceRefresh.current ? "&refresh=1" : "";
    forceRefresh.current = false;
    let cancelled = false;
    // Standard fetch-on-change; `cancelled` drops a stale period's response.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    setError(null);
    apiFetch(`/api/profitability/?from=${from}&to=${to}${refresh}`)
      .then(async (res) => {
        if (!res.ok) throw new Error("No se pudo cargar la rentabilidad.");
        const json = await res.json();
        if (!cancelled) setData(json);
      })
      .catch((err) => !cancelled && setError(err.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [from, to, isManagement, reload]);

  // Each fact's value for a dimension: what it's filtered and grouped by.
  const valueOf = useMemo(() => {
    const products = data?.products ?? {};
    return (f: Fact, dim: Dim): string => {
      const product = f[3] === null ? null : products[f[3]];
      switch (dim) {
        case "zone":
          return f[1];
        case "category":
          return product?.category ?? NO_PRODUCT;
        case "brand":
          return product?.brand ?? NO_PRODUCT;
        case "product":
          return f[3] === null ? NO_PRODUCT : String(f[3]);
        case "client":
          return String(f[2]);
        case "month":
          return f[0];
      }
    };
  }, [data]);

  const labelOf = (dim: Dim, value: string) => {
    if (!data) return value;
    switch (dim) {
      case "zone":
        return zoneLabel(value);
      case "category":
        return CATEGORY_LABELS[value] ?? value;
      case "product": {
        const p = data.products[value];
        return p ? `${p.code} · ${p.name}` : value;
      }
      case "client":
        return data.clients[value] ?? `Cliente ${value}`;
      case "month":
        return formatMonth(value);
      default:
        return value;
    }
  };

  const filtered = useMemo(() => {
    if (!data) return [];
    const active = Object.entries(filters) as [Dim, string][];
    return data.facts.filter((f) => active.every(([dim, v]) => valueOf(f, dim) === v));
  }, [data, filters, valueOf]);

  // Options for each filter come from the rows the *other* filters leave, so
  // picking Zona 2 only offers the lines Zona 2 actually sold.
  const options = (dim: Exclude<Dim, "month">) => {
    if (!data) return [];
    const others = (Object.entries(filters) as [Dim, string][]).filter(([d]) => d !== dim);
    const values = new Set<string>();
    for (const f of data.facts) {
      if (others.every(([d, v]) => valueOf(f, d) === v)) values.add(valueOf(f, dim));
    }
    const list = [...values].map((v) => ({ value: v, label: labelOf(dim, v) }));
    if (dim === "zone") return list.sort((a, b) => ZONE_ORDER.indexOf(a.value as Zone) - ZONE_ORDER.indexOf(b.value as Zone));
    return list.sort((a, b) => a.label.localeCompare(b.label, "es"));
  };

  const totals = useMemo(() => {
    const t = { net: 0, cost: 0, kg: 0, estimatedKg: 0 };
    for (const f of filtered) {
      t.net += f[5];
      t.cost += f[6];
      t.kg += f[7];
      if (f[3] !== null && data?.products[f[3]]?.source === "estimado") t.estimatedKg += f[7];
    }
    return t;
  }, [filtered, data]);

  const groups = useMemo(() => {
    const map = new Map<string, Group>();
    for (const f of filtered) {
      const key = valueOf(f, groupBy);
      const g = map.get(key) ?? { key, label: labelOf(groupBy, key), net: 0, cost: 0, kg: 0 };
      g.net += f[5];
      g.cost += f[6];
      g.kg += f[7];
      map.set(key, g);
    }
    // A product sold and fully returned nets to nothing; it only clutters the list.
    return [...map.values()].filter((g) => Math.abs(g.net) >= 0.5 || Math.abs(g.cost) >= 0.5 || Math.abs(g.kg) >= 0.5);
    // labelOf only reads `data`, already a dependency through valueOf.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtered, groupBy, valueOf]);

  const columns = useMemo(
    () => ({
      label: { value: (g: Group) => (groupBy === "month" ? g.key : g.label), first: "asc" as const },
      net: { value: (g: Group) => g.net, first: "desc" as const },
      profit: { value: (g: Group) => g.net - g.cost, first: "desc" as const },
      margin: { value: (g: Group) => (g.net ? (g.net - g.cost) / g.net : null), first: "desc" as const },
      kg: { value: (g: Group) => g.kg, first: "desc" as const },
      perKg: { value: (g: Group) => (g.kg >= 1 ? (g.net - g.cost) / g.kg : null), first: "desc" as const },
    }),
    [groupBy],
  );
  const { sorted, sortKey, sortDir, toggle } = useSort(groups, columns, { key: "net", dir: "desc" });

  // Clicking a row filters by it and moves on to the next breakdown not yet filtered.
  const drill = (g: Group) => {
    if (groupBy === "month") return;
    const next = { ...filters, [groupBy]: g.key };
    setFilters(next);
    const order: Dim[] = ["zone", "category", "brand", "product", "client"];
    setGroupBy(order.find((d) => d !== groupBy && !(d in next)) ?? "month");
  };

  if (!authLoading && !isManagement) {
    return (
      <main className="max-w-7xl mx-auto w-full p-4 sm:p-6">
        <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-gray-300 bg-white py-16 text-center">
          <p className="text-sm font-medium text-gray-700">No tiene permiso para ver la rentabilidad.</p>
          <a href="/login" className="text-sm font-medium text-slate-900 underline">
            Iniciar sesión
          </a>
        </div>
      </main>
    );
  }

  const profit = totals.net - totals.cost;
  const activeFilters = Object.entries(filters) as [Exclude<Dim, "month">, string][];

  return (
    <main className="max-w-7xl mx-auto w-full p-4 sm:p-6 flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold text-gray-900">Rentabilidad</h1>
        <p className="text-sm text-gray-500">
          Utilidad bruta (venta sin IVA menos costo del ERP) por zona, línea, marca, producto y cliente. Mismas
          facturas que Ventas y Comisiones, sin anticipos; las devoluciones y notas de crédito se descuentan en su mes.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2 sm:gap-3">
        <span className="text-sm text-gray-500">De</span>
        <MonthControl month={from} onChange={(m) => (setFrom(m), m > to && setTo(m))} />
        <span className="text-sm text-gray-500">a</span>
        <MonthControl month={to} onChange={(m) => (setTo(m), m < from && setFrom(m))} />
        <Button
          size="sm"
          variant="outline"
          className="h-9 sm:h-8"
          disabled={loading}
          title="Actualizar con los datos más recientes del ERP"
          aria-label="Actualizar"
          onClick={() => {
            forceRefresh.current = true;
            setReload((n) => n + 1);
          }}
        >
          <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} aria-hidden />
          <span className="hidden sm:inline">Actualizar</span>
        </Button>
        <Button size="sm" variant="outline" className="h-9 sm:h-8" disabled={!data} onClick={() => setWeightsOpen(true)}>
          <Scale className="w-4 h-4" aria-hidden />
          Pesos
        </Button>
      </div>

      {error && <p className="text-sm text-red-700">{error}</p>}

      {data && (
        <>
          <div className="flex flex-wrap items-center gap-2">
            {(["zone", "category", "brand"] as const).map((dim) => (
              <select
                key={dim}
                value={filters[dim] ?? ""}
                aria-label={DIMS.find((d) => d.key === dim)!.label}
                onChange={(e) =>
                  setFilters((f) => {
                    const next = { ...f };
                    if (e.target.value) next[dim] = e.target.value;
                    else delete next[dim];
                    return next;
                  })
                }
                className="h-9 max-w-56 rounded-md border border-input bg-background px-2 text-sm"
              >
                <option value="">{dim === "zone" ? "Todas las zonas" : dim === "category" ? "Todas las líneas" : "Todas las marcas"}</option>
                {options(dim).map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            ))}
            {activeFilters
              .filter(([dim]) => dim === "product" || dim === "client")
              .map(([dim, value]) => (
                <span
                  key={dim}
                  className="inline-flex max-w-full items-center gap-1 rounded-full border bg-gray-50 py-1 pl-3 pr-1 text-sm"
                >
                  <span className="truncate">{labelOf(dim, value)}</span>
                  <button
                    type="button"
                    aria-label="Quitar filtro"
                    className="rounded-full p-1 hover:bg-gray-200"
                    onClick={() => setFilters((f) => without(f, dim))}
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </span>
              ))}
            {activeFilters.length > 0 && (
              <Button size="sm" variant="ghost" onClick={() => setFilters({})}>
                Quitar filtros
              </Button>
            )}
          </div>

          <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
            <Tile label="Ventas" value={formatMoney(totals.net)} />
            <Tile label="Utilidad bruta" value={formatMoney(profit)} />
            <Tile label="Margen bruto" value={totals.net ? percent(profit / totals.net) : "-"} />
            <Tile label="Peso vendido" value={tonnes(totals.kg)} />
            <Tile label="Utilidad por kg" value={totals.kg >= 1 ? formatMoney(profit / totals.kg) : "-"} />
          </div>

          <Card>
            <CardHeader className="p-3 sm:p-4 gap-3">
              <Tabs value={groupBy} onValueChange={(v) => setGroupBy(v as Dim)}>
                <TabsList className="h-auto flex-wrap">
                  {DIMS.map((d) => (
                    <TabsTrigger key={d.key} value={d.key}>
                      Por {d.label.toLowerCase()}
                    </TabsTrigger>
                  ))}
                </TabsList>
              </Tabs>
              {groupBy !== "month" && (
                <CardDescription>Toque una fila para ver solo {DIMS.find((d) => d.key === groupBy)!.one}.</CardDescription>
              )}
            </CardHeader>
            <Table>
              <TableHeader>
                <TableRow>
                  <SortableHead label={DIMS.find((d) => d.key === groupBy)!.label} column="label" sortKey={sortKey} sortDir={sortDir} onSort={toggle} />
                  <SortableHead label="Ventas" column="net" align="right" sortKey={sortKey} sortDir={sortDir} onSort={toggle} />
                  <SortableHead label="Utilidad bruta" column="profit" align="right" sortKey={sortKey} sortDir={sortDir} onSort={toggle} className={HIDE_BELOW_SM} />
                  <SortableHead label="Margen" column="margin" align="right" sortKey={sortKey} sortDir={sortDir} onSort={toggle} />
                  <SortableHead label="Peso" column="kg" align="right" sortKey={sortKey} sortDir={sortDir} onSort={toggle} className={HIDE_BELOW_MD} />
                  <SortableHead label="Utilidad / kg" column="perKg" align="right" sortKey={sortKey} sortDir={sortDir} onSort={toggle} className={HIDE_BELOW_MD} />
                  {groupBy === "product" && <TableHead className="w-px" />}
                </TableRow>
              </TableHeader>
              <TableBody>
                {sorted.length === 0 && <EmptyRow colSpan={groupBy === "product" ? 7 : 6}>Sin ventas con estos filtros.</EmptyRow>}
                {sorted.map((g) => (
                  <TableRow key={g.key} className={cn(groupBy !== "month" && "cursor-pointer")} onClick={() => drill(g)}>
                    <TableCell className="max-w-72 truncate" title={g.label}>
                      {g.label}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{formatMoney(g.net)}</TableCell>
                    <TableCell className={cn("text-right tabular-nums", HIDE_BELOW_SM)}>{formatMoney(g.net - g.cost)}</TableCell>
                    <TableCell className={cn("text-right tabular-nums", g.net - g.cost < 0 && "text-red-700")}>
                      {g.net ? percent((g.net - g.cost) / g.net) : "-"}
                    </TableCell>
                    <TableCell className={cn("text-right tabular-nums", HIDE_BELOW_MD)}>{g.kg ? tonnes(g.kg) : "-"}</TableCell>
                    <TableCell className={cn("text-right tabular-nums", HIDE_BELOW_MD)}>
                      {g.kg >= 1 ? formatMoney((g.net - g.cost) / g.kg) : "-"}
                    </TableCell>
                    {groupBy === "product" && (
                      <TableCell className="py-0 text-right">
                        {g.key !== NO_PRODUCT && (
                          <Button
                            size="sm"
                            variant="ghost"
                            className="h-7 text-gray-500"
                            title="Dejar este producto fuera de la rentabilidad (ventas únicas que distorsionan los números)"
                            onClick={(e) => {
                              e.stopPropagation();
                              if (window.confirm(`¿Dejar fuera "${g.label}"? Se puede volver a incluir después.`)) {
                                setExcluded(g.key, true);
                              }
                            }}
                          >
                            Excluir
                          </Button>
                        )}
                      </TableCell>
                    )}
                  </TableRow>
                ))}
                {sorted.length > 1 && (
                  <TableRow className="font-medium hover:bg-transparent">
                    <TableCell>Total</TableCell>
                    <TableCell className="text-right tabular-nums">{formatMoney(totals.net)}</TableCell>
                    <TableCell className={cn("text-right tabular-nums", HIDE_BELOW_SM)}>{formatMoney(profit)}</TableCell>
                    <TableCell className="text-right tabular-nums">{totals.net ? percent(profit / totals.net) : "-"}</TableCell>
                    <TableCell className={cn("text-right tabular-nums", HIDE_BELOW_MD)}>{tonnes(totals.kg)}</TableCell>
                    <TableCell className={cn("text-right tabular-nums", HIDE_BELOW_MD)}>
                      {totals.kg >= 1 ? formatMoney(profit / totals.kg) : "-"}
                    </TableCell>
                    {groupBy === "product" && <TableCell />}
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </Card>

          {excludeError && <p className="text-sm text-red-700">{excludeError}</p>}
          <ul className="list-disc pl-5 text-xs text-gray-500 space-y-1">
            {data.excluded.length > 0 && (
              <li>
                {data.excluded.length === 1 ? "1 producto excluido" : `${data.excluded.length} productos excluidos`} de
                todas las cifras.{" "}
                <button type="button" className="underline hover:text-gray-900" onClick={() => setExcludedOpen(true)}>
                  Ver
                </button>
              </li>
            )}
            <li>
              Los anticipos no cuentan como venta: la factura del anticipo y la nota de crédito que lo aplica se dejan
              fuera, y la factura final cuenta completa en su mes. Por eso algunos meses difieren de Ventas.
            </li>
            <li>
              Las demás notas de crédito no traen producto en el ERP: cada una se reparte entre las partidas de la factura
              a la que se aplicó, en proporción a su importe.
            </li>
            <li>Los servicios no tienen costo en el ERP, por eso su margen sale al 100%.</li>
            <li>
              El peso se toma del nombre del producto, del catálogo GEA o de lo capturado en Pesos; el{" "}
              {totals.kg ? percent(totals.estimatedKg / totals.kg) : "0%"} de este peso es estimado.
            </li>
          </ul>
        </>
      )}

      {data && (
        <Dialog open={excludedOpen} onOpenChange={setExcludedOpen}>
          <DialogContent className="max-w-xl">
            <DialogHeader>
              <DialogTitle>Productos excluidos</DialogTitle>
            </DialogHeader>
            <ul className="divide-y">
              {data.excluded.length === 0 && <li className="py-3 text-sm text-gray-500">Ninguno.</li>}
              {data.excluded.map((id) => (
                <li key={id} className="flex items-center justify-between gap-3 py-2 text-sm">
                  <span className="truncate">{labelOf("product", String(id))}</span>
                  <Button size="sm" variant="outline" onClick={() => setExcluded(String(id), false)}>
                    Volver a incluir
                  </Button>
                </li>
              ))}
            </ul>
          </DialogContent>
        </Dialog>
      )}

      {data && (
        <WeightsDialog
          open={weightsOpen}
          onOpenChange={setWeightsOpen}
          data={data}
          facts={filtered}
          onSaved={() => setReload((n) => n + 1)}
        />
      )}
    </main>
  );
}

// Products in the current view with their kg per unit; estimated ones first, by
// how much weight they carry. A typed weight is stored and wins from then on.
function WeightsDialog({
  open,
  onOpenChange,
  data,
  facts,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  data: Profitability;
  facts: Fact[];
  onSaved: () => void;
}) {
  const [onlyEstimated, setOnlyEstimated] = useState(true);
  const [search, setSearch] = useState("");
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const rows = useMemo(() => {
    const units = new Map<string, number>();
    for (const f of facts) if (f[3] !== null) units.set(String(f[3]), (units.get(String(f[3])) ?? 0) + f[4]);
    const q = search.trim().toLowerCase();
    return [...units.entries()]
      .map(([id, u]) => ({ id, units: u, ...data.products[id] }))
      .filter((p) => p.source !== "servicio" && p.units > 0)
      .filter((p) => !onlyEstimated || p.source === "estimado" || p.source === "manual")
      .filter((p) => !q || p.code.toLowerCase().includes(q) || p.name.toLowerCase().includes(q))
      .sort((a, b) => b.units * b.kg - a.units * a.kg);
  }, [facts, data, onlyEstimated, search]);

  const save = async (id: string, value: string | null) => {
    setSaving(id);
    setError(null);
    const res = await apiFetch("/api/profitability/weights/", {
      method: "POST",
      body: JSON.stringify({ product_id: Number(id), kg: value }),
    });
    setSaving(null);
    if (!res.ok) {
      const json = await res.json().catch(() => ({}));
      setError(json.error ?? "No se pudo guardar el peso.");
      return;
    }
    setDrafts((d) => without(d, id));
    onSaved();
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[85vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>Peso por unidad de venta</DialogTitle>
        </DialogHeader>
        <div className="flex flex-wrap items-center gap-3">
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar código o nombre"
            className="h-9 w-64"
          />
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={onlyEstimated} onChange={(e) => setOnlyEstimated(e.target.checked)} />
            Solo estimados y capturados
          </label>
        </div>
        {error && <p className="text-sm text-red-700">{error}</p>}
        <div className="overflow-y-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Producto</TableHead>
                <TableHead className={HIDE_BELOW_SM}>Origen</TableHead>
                <TableHead className="text-right">Unidades</TableHead>
                <TableHead className="text-right">Kg por unidad</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.length === 0 && <EmptyRow colSpan={4}>No hay productos que mostrar.</EmptyRow>}
              {rows.map((p) => {
                const draft = drafts[p.id];
                return (
                  <TableRow key={p.id}>
                    <TableCell className="max-w-80">
                      <div className="truncate" title={p.name}>
                        {p.name}
                      </div>
                      <div className="text-xs text-gray-500">{p.code}</div>
                    </TableCell>
                    <TableCell className={HIDE_BELOW_SM}>{SOURCE_LABELS[p.source]}</TableCell>
                    <TableCell className="text-right tabular-nums">{p.units.toLocaleString("es-MX")}</TableCell>
                    <TableCell className="text-right">
                      <form
                        className="inline-flex items-center gap-1"
                        onSubmit={(e) => {
                          e.preventDefault();
                          if (draft !== undefined && draft !== "") save(p.id, draft);
                        }}
                      >
                        <Input
                          type="number"
                          inputMode="decimal"
                          min={0}
                          step="any"
                          aria-label={`Kg por unidad de ${p.code}`}
                          value={draft ?? String(p.kg)}
                          onChange={(e) => setDrafts((d) => ({ ...d, [p.id]: e.target.value }))}
                          className="h-8 w-24 text-right"
                        />
                        {draft !== undefined && draft !== String(p.kg) && (
                          <Button type="submit" size="sm" className="h-8" disabled={saving === p.id}>
                            Guardar
                          </Button>
                        )}
                        {p.source === "manual" && draft === undefined && (
                          <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            className="h-8"
                            disabled={saving === p.id}
                            title="Volver al peso automático"
                            onClick={() => save(p.id, null)}
                          >
                            Quitar
                          </Button>
                        )}
                      </form>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      </DialogContent>
    </Dialog>
  );
}

