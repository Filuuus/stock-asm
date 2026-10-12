"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Calculator, EyeOff, FileText, RefreshCw, Scale, Settings2, Trash2, X } from "lucide-react";
import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  EmptyRow, HIDE_BELOW_LG, HIDE_BELOW_MD, HIDE_BELOW_SM, SortableHead, useSort,
} from "@/components/sortable-table";
import { MonthControl } from "@/components/date-controls";
import { CATEGORY_LABELS } from "@/components/catalog/CatalogFilters";
import ClientLink from "@/components/facturas/ClientLink";
import InvoiceLink from "@/components/facturas/InvoiceLink";
import { formatDay, formatMonth, isoToDate, monthToISO } from "@/lib/dates";
import { zoneLabel, ZONE_ORDER } from "@/lib/zones";
import { cn, formatMoney } from "@/lib/utils";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/hooks/use-auth";
import type { Zone } from "@/types/commissions";

// [month "YYYY-MM", zone, client id, product id (null = credit note never applied), units, net, cost, kg,
//  full commission, paid commission, supplier discount, route cost split by kg, route cost split by piece,
//  import cost]
type Fact = [
  string, string, number, number | null, number, number, number, number, number, number, number, number, number,
  number,
];
type WeightSource = "manual" | "nombre" | "GEA" | "unidad" | "estimado" | "servicio";

interface Product {
  code: string;
  name: string;
  brand: string;
  category: string;
  kg: number; // per sale unit
  source: WeightSource;
}

type Pools = Record<string, Record<string, number>>; // pool -> component -> amount

interface Profitability {
  facts: Fact[];
  excluded: number[]; // product ids left out altogether, with their returns and credit notes
  products: Record<string, Product>;
  clients: Record<string, string>;
  route_costs: Record<string, Pools>; // month -> pools
  unallocated: Record<string, Record<string, number>>; // month -> pool -> amount with nothing to land on
  gps_since: string | null;
  workbook_through: string | null; // last month of the accountant's vehicle workbook imported
  imports: { cost: number; purchases: number; rate: number }; // the period's import costs over foreign purchases
}

type Dim = "zone" | "category" | "brand" | "product" | "client" | "month";
type Filters = Partial<Record<Exclude<Dim, "month">, string>>;
type CommissionMode = "posibles" | "pagadas";
// A negotiation what-if on a brand, line or product: percentages typed as numbers (5 = 5%).
interface Adjustment {
  dim: "brand" | "category" | "product";
  key: string;
  discount: number; // supplier discount on its cost (import costs shrink with it: they're a rate on cost)
  price: number; // change in our selling price
  volume: number; // change in units sold
}
const NO_ADJUSTMENT = { discount: 0, price: 0, volume: 0 };
type RouteKey = "kg" | "pieza";

const DIMS: { key: Dim; label: string; one: string }[] = [
  { key: "zone", label: "Zona", one: "esa zona" },
  { key: "category", label: "Línea", one: "esa línea" },
  { key: "brand", label: "Marca", one: "esa marca" },
  { key: "product", label: "Producto", one: "ese producto" },
  { key: "client", label: "Cliente", one: "ese cliente" },
  { key: "month", label: "Mes", one: "ese mes" },
];
const POOL_LABELS: Record<string, string> = {
  ZONA1: "Zona 1",
  ZONA2: "Zona 2",
  ALMACEN: "Almacén",
  SERVICIOS: "Servicios",
};
const NO_PRODUCT = "Sin producto";
const SOURCE_LABELS: Record<WeightSource, string> = {
  manual: "Capturado",
  nombre: "Del nombre",
  GEA: "Catálogo GEA",
  unidad: "Unidad del ERP",
  estimado: "Estimado",
  servicio: "Servicio",
};
// Categorical slots 1 and 2 of the dataviz palette, as on Ventas (validated as a pair).
const COLOR_GROSS = "#2a78d6";
const COLOR_NET = "#eb6834";

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

// "$13,530,618": the breakdown table drops the cents so ten columns fit the owner's tablet.
function pesos(value: number) {
  return value.toLocaleString("es-MX", { style: "currency", currency: "MXN", maximumFractionDigits: 0 });
}

// "$4.2 M" - axis ticks only.
function compactMoney(value: number) {
  return `$${value.toLocaleString("es-MX", { notation: "compact", maximumFractionDigits: 1 })}`;
}

const MONTH_ABBR = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];

function monthShort(month: string) {
  return `${MONTH_ABBR[Number(month.slice(5)) - 1]} ${month.slice(2, 4)}`;
}

interface Sums {
  net: number;
  cost: number;
  commission: number;
  route: number;
  kg: number;
}

interface Group extends Sums {
  key: string;
  label: string;
  dropped?: boolean; // a what-if row: shown with its real figures, left out of the totals
}

const gross = (s: Sums) => s.net - s.cost;
// What a row adds before the shared route costs: what would be lost by not selling it.
const contribution = (s: Sums) => s.net - s.cost - s.commission;
const result = (s: Sums) => s.net - s.cost - s.commission - s.route;

function emptySums(): Sums {
  return { net: 0, cost: 0, commission: 0, route: 0, kg: 0 };
}

function Tile({ label, value, sub, change, changeLabel = "vs año anterior" }: {
  label: string;
  value: string;
  sub?: string;
  change?: number | null;
  changeLabel?: string;
}) {
  return (
    <Card>
      <CardHeader className="p-3 sm:p-4 space-y-1">
        <CardDescription className="text-xs sm:text-sm">{label}</CardDescription>
        <CardTitle className="text-base sm:text-xl">{value}</CardTitle>
        {sub && <p className="text-xs text-gray-500">{sub}</p>}
        {change !== undefined && change !== null && (
          <p className={cn("text-xs", change >= 0 ? "text-emerald-700" : "text-red-700")}>
            {change >= 0 ? "+" : ""}
            {percent(change)} {changeLabel}
          </p>
        )}
      </CardHeader>
    </Card>
  );
}

// Change against last year's same months, or null when last year was zero or of the other sign.
function change(current: number, previous: number | undefined) {
  if (previous === undefined || previous <= 0) return null;
  return (current - previous) / previous;
}

export default function ProfitabilityView() {
  const { loading: authLoading, isManagement } = useAuth();
  const [to, setTo] = useState(lastCompleteMonth);
  const [from, setFrom] = useState(() => shiftMonth(lastCompleteMonth(), -11));
  const [data, setData] = useState<Profitability | null>(null);
  const [previous, setPrevious] = useState<Profitability | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  const forceRefresh = useRef(false);
  const [filters, setFilters] = useState<Filters>({});
  const [groupBy, setGroupBy] = useState<Dim>("zone");
  // Defaults are management's own criteria (Bionat report v2): every commission an invoice could earn,
  // supplier credit notes left out.
  const [commissionMode, setCommissionMode] = useState<CommissionMode>("posibles");
  const [supplierDiscounts, setSupplierDiscounts] = useState(false);
  const [routeKey, setRouteKey] = useState<RouteKey>("kg");
  // Freight abroad, duties and brokers are real costs of imported goods, so they count unless switched off.
  const [importCosts, setImportCosts] = useState(true);
  const [search, setSearch] = useState("");
  const [weightsOpen, setWeightsOpen] = useState(false);
  const [excludedOpen, setExcludedOpen] = useState(false);
  const [invoicesOf, setInvoicesOf] = useState<string | null>(null); // product id whose invoices are listed
  const [setupOpen, setSetupOpen] = useState(false);
  const [excludeError, setExcludeError] = useState<string | null>(null);
  // What-if: products imagined not sold (per viewer, not saved), and the server's recomputation without them.
  const [dropped, setDropped] = useState<string[]>([]);
  const [scenario, setScenario] = useState<Profitability | null>(null);
  // Negotiation simulator (in the browser, instant; not saved).
  const [adjustments, setAdjustments] = useState<Adjustment[]>([]);
  const [simOpen, setSimOpen] = useState(false);
  const [paretoDim, setParetoDim] = useState<"product" | "client">("product");

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
    const load = (a: string, b: string) =>
      apiFetch(`/api/profitability/?from=${a}&to=${b}${refresh}`).then(async (res) => {
        if (!res.ok) throw new Error("No se pudo cargar la rentabilidad.");
        return res.json();
      });
    // Standard fetch-on-change; `cancelled` drops a stale period's response.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    setError(null);
    Promise.all([load(from, to), load(shiftMonth(from, -12), shiftMonth(to, -12))])
      .then(([current, prior]) => {
        if (cancelled) return;
        setData(current);
        setPrevious(prior);
      })
      .catch((err) => !cancelled && setError(err.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [from, to, isManagement, reload]);

  useEffect(() => {
    if (!isManagement || dropped.length === 0) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setScenario(null);
      return;
    }
    let cancelled = false;
    apiFetch(`/api/profitability/?from=${from}&to=${to}&drop=${dropped.join(",")}`)
      .then(async (res) => {
        if (!res.ok) throw new Error("No se pudo calcular el escenario.");
        const json = await res.json();
        if (!cancelled) setScenario(json);
      })
      .catch((err) => !cancelled && setError(err.message));
    return () => {
      cancelled = true;
    };
  }, [from, to, isManagement, reload, dropped]);

  // A fact's value for a dimension: what it's filtered and grouped by. Takes the product list
  // of its own response, so last year's facts resolve too.
  const valueOf = (f: Fact, dim: Dim, products: Record<string, Product>): string => {
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

  // The simulator's changes that apply to a fact, combined when several match (a brand and one of its products).
  const adjustmentFor = (f: Fact) => {
    if (!data || adjustments.length === 0) return NO_ADJUSTMENT;
    let cost = 1, price = 1, volume = 1;
    for (const a of adjustments) {
      if (valueOf(f, a.dim, data.products) !== a.key) continue;
      cost *= 1 - a.discount / 100;
      price *= 1 + a.price / 100;
      volume *= 1 + a.volume / 100;
    }
    return { discount: 1 - cost, price: price - 1, volume: volume - 1 };
  };

  // The toggles decide which cost columns count; `simulate` applies the negotiation simulator. Route costs
  // don't move with it: salaries, trucks and rent stay whatever is sold.
  const add = (s: Sums, f: Fact, simulate = true) => {
    const a = simulate ? adjustmentFor(f) : NO_ADJUSTMENT;
    const volume = 1 + a.volume, price = 1 + a.price;
    s.net += f[5] * price * volume;
    s.cost += (f[6] - (supplierDiscounts ? f[10] : 0) + (importCosts ? f[13] : 0)) * (1 - a.discount) * volume;
    s.commission += (commissionMode === "pagadas" ? f[9] : f[8]) * price * volume; // commissions are a % of the sale
    s.route += routeKey === "kg" ? f[11] : f[12];
    s.kg += f[7] * volume;
  };

  const applyFilters = (d: Profitability | null) => {
    if (!d) return [];
    const active = Object.entries(filters) as [Dim, string][];
    return d.facts.filter((f) => active.every(([dim, v]) => valueOf(f, dim, d.products) === v));
  };
  // What the page shows: the what-if when there is one, else the real figures.
  const scenarioOn = dropped.length > 0 && scenario !== null;
  const shown = scenarioOn ? scenario : data;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const filtered = useMemo(() => applyFilters(shown), [shown, filters]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const filteredReal = useMemo(() => applyFilters(data), [data, filters]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const filteredPrevious = useMemo(() => applyFilters(previous), [previous, filters]);

  // Options for each filter come from the rows the *other* filters leave, so
  // picking Zona 2 only offers the lines Zona 2 actually sold.
  const options = (dim: Exclude<Dim, "month">) => {
    if (!data) return [];
    const others = (Object.entries(filters) as [Dim, string][]).filter(([d]) => d !== dim);
    const values = new Set<string>();
    for (const f of data.facts) {
      if (others.every(([d, v]) => valueOf(f, d, data.products) === v)) values.add(valueOf(f, dim, data.products));
    }
    const list = [...values].map((v) => ({ value: v, label: labelOf(dim, v) }));
    if (dim === "zone") return list.sort((a, b) => ZONE_ORDER.indexOf(a.value as Zone) - ZONE_ORDER.indexOf(b.value as Zone));
    return list.sort((a, b) => a.label.localeCompare(b.label, "es"));
  };

  // Client and product search: every one in the period, by name or code.
  const searchOptions = useMemo(() => {
    if (!data) return new Map<string, [Dim, string]>();
    const map = new Map<string, [Dim, string]>();
    for (const [id, name] of Object.entries(data.clients)) map.set(`Cliente: ${name}`, ["client", id]);
    for (const [id, p] of Object.entries(data.products)) {
      if (!data.excluded.includes(Number(id))) map.set(`Producto: ${p.code} · ${p.name}`, ["product", id]);
    }
    return map;
  }, [data]);

  const sumOf = (facts: Fact[], simulate = true) => {
    const s = emptySums();
    for (const f of facts) add(s, f, simulate);
    return s;
  };
  const simOn = adjustments.some((a) => a.discount || a.price || a.volume);
  // Against the real figures whenever a what-if or a simulation is on, else against last year.
  const versusReal = scenarioOn || simOn;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const totals = useMemo(() => sumOf(filtered), [filtered, commissionMode, supplierDiscounts, routeKey, importCosts, adjustments]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const totalsReal = useMemo(() => sumOf(filteredReal, false), [filteredReal, commissionMode, supplierDiscounts, routeKey, importCosts]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const totalsPrevious = useMemo(() => sumOf(filteredPrevious, false), [filteredPrevious, commissionMode, supplierDiscounts, routeKey, importCosts]);
  const estimatedKg = useMemo(
    () => filtered.reduce((t, f) => t + (f[3] !== null && data?.products[f[3]]?.source === "estimado" ? f[7] : 0), 0),
    [filtered, data],
  );

  const groups = useMemo(() => {
    if (!data) return [];
    const map = new Map<string, Group>();
    for (const f of filtered) {
      const key = valueOf(f, groupBy, data.products);
      const g = map.get(key) ?? { key, label: labelOf(groupBy, key), ...emptySums() };
      add(g, f);
      map.set(key, g);
    }
    // Groups the what-if took out entirely still list, greyed, with their real figures.
    if (scenarioOn) {
      const gone = new Set(dropped);
      for (const f of filteredReal) {
        if (f[3] === null || !gone.has(String(f[3]))) continue;
        const key = valueOf(f, groupBy, data.products);
        if (map.has(key) && !map.get(key)!.dropped) continue;
        const g = map.get(key) ?? { key, label: labelOf(groupBy, key), dropped: true, ...emptySums() };
        add(g, f, false);
        map.set(key, g);
      }
    }
    // A product sold and fully returned nets to nothing; it only clutters the list.
    return [...map.values()].filter((g) => [g.net, g.cost, g.kg, g.commission, g.route].some((v) => Math.abs(v) >= 0.5));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtered, filteredReal, groupBy, data, commissionMode, supplierDiscounts, routeKey, importCosts, scenarioOn, dropped, adjustments]);

  // What-if checkboxes, on line, brand and product rows: the products behind each row.
  const checkable = groupBy === "category" || groupBy === "brand" || groupBy === "product";
  const groupProducts = useMemo(() => {
    const map = new Map<string, Set<string>>();
    if (!data || !checkable) return map;
    for (const f of data.facts) {
      if (f[3] === null) continue;
      const key = valueOf(f, groupBy, data.products);
      if (!map.has(key)) map.set(key, new Set());
      map.get(key)!.add(String(f[3]));
    }
    return map;
  }, [data, groupBy, checkable]);
  const droppedCount = (key: string) => [...(groupProducts.get(key) ?? [])].filter((id) => dropped.includes(id)).length;
  const toggleDrop = (key: string) => {
    const ids = [...(groupProducts.get(key) ?? [])];
    // A fully kept row drops all its products; a partly or fully dropped one brings them all back.
    setDropped((d) => (droppedCount(key) === 0 ? [...new Set([...d, ...ids])] : d.filter((id) => !ids.includes(id))));
  };

  // Months of the period, for the chart: gross and net result per month.
  const chart = useMemo(() => {
    const byMonth = new Map<string, Sums>();
    for (let m = from; m <= to; m = shiftMonth(m, 1)) byMonth.set(m, emptySums());
    for (const f of filtered) {
      const s = byMonth.get(f[0]);
      if (s) add(s, f);
    }
    return [...byMonth.entries()].map(([m, s]) => ({ label: monthShort(m), bruta: gross(s), neta: result(s) }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtered, from, to, commissionMode, supplierDiscounts, routeKey, importCosts, adjustments]);

  // The period's route costs by pool and component (not affected by the filters).
  const pools = useMemo(() => {
    const out: Record<string, Record<string, number>> = {};
    for (const monthPools of Object.values(data?.route_costs ?? {})) {
      for (const [pool, components] of Object.entries(monthPools)) {
        out[pool] ??= {};
        for (const [k, v] of Object.entries(components)) out[pool][k] = (out[pool][k] ?? 0) + v;
      }
    }
    return out;
  }, [data]);
  const poolComponents = [...new Set(Object.values(pools).flatMap((c) => Object.keys(c)))].sort();
  const unallocated = Object.values(data?.unallocated ?? {}).reduce(
    (t, p) => t + Object.values(p).reduce((a, b) => a + b, 0),
    0,
  );

  // "Qué haría falta": for every loss-making brand, line or product in view, the supplier discount that
  // would bring it to zero - on its own (contribution) and also covering its share of route costs (net).
  // The selling price stays: the market won't take an increase (management, 2026-10-12).
  const breakEven = useMemo(() => {
    if (!checkable) return [];
    return groups
      .filter((g) => !g.dropped && g.cost > 0 && result(g) < 0)
      .map((g) => ({
        ...g,
        forContribution: contribution(g) < 0 ? -contribution(g) / g.cost : 0,
        forNet: -result(g) / g.cost,
      }))
      .sort((a, b) => result(a) - result(b));
  }, [groups, checkable]);

  // Concentration: how few products (or clients) bring most of the contribution.
  const pareto = useMemo(() => {
    if (!data) return null;
    const by = new Map<string, Sums>();
    for (const f of filtered) {
      const key = valueOf(f, paretoDim, data.products);
      if (!by.has(key)) by.set(key, emptySums());
      add(by.get(key)!, f);
    }
    const items = [...by.values()].map(contribution).sort((a, b) => b - a);
    const total = items.reduce((a, b) => a + b, 0);
    if (items.length < 2 || total <= 0) return null;
    let running = 0;
    let to80 = 0;
    const points = items.map((c, i) => {
      running += c;
      if (!to80 && running >= total * 0.8) to80 = i + 1;
      return { share: ((i + 1) / items.length) * 100, cumulative: (running / total) * 100 };
    });
    const losers = items.filter((c) => c < 0);
    return {
      count: items.length, to80, points,
      peak: Math.max(...points.map((p) => p.cumulative)),
      losers: losers.length, lost: losers.reduce((a, b) => a + b, 0),
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtered, paretoDim, data, commissionMode, supplierDiscounts, routeKey, importCosts, adjustments]);

  const addAdjustment = (a: Partial<Adjustment>) => {
    const dim = a.dim ?? (groupBy === "category" || groupBy === "product" ? groupBy : "brand");
    setAdjustments((list) => [...list, { dim, key: a.key ?? "", discount: 0, price: 0, volume: 0, ...a }]);
    setSimOpen(true);
  };
  const setAdjustment = (i: number, patch: Partial<Adjustment>) =>
    setAdjustments((list) => list.map((a, j) => (j === i ? { ...a, ...patch } : a)));
  // One adjustment row's real figures, for its hints.
  const adjustmentBase = (a: Adjustment) => {
    const s = emptySums();
    if (data) for (const f of filteredReal) if (valueOf(f, a.dim, data.products) === a.key) add(s, f, false);
    return s;
  };

  const columns = useMemo(
    () => ({
      label: { value: (g: Group) => (groupBy === "month" ? g.key : g.label), first: "asc" as const },
      net: { value: (g: Group) => g.net, first: "desc" as const },
      gross: { value: gross, first: "desc" as const },
      commission: { value: (g: Group) => g.commission, first: "desc" as const },
      contribution: { value: contribution, first: "desc" as const },
      route: { value: (g: Group) => g.route, first: "desc" as const },
      result: { value: result, first: "desc" as const },
      margin: { value: (g: Group) => (g.net ? result(g) / g.net : null), first: "desc" as const },
      kg: { value: (g: Group) => g.kg, first: "desc" as const },
      perKg: { value: (g: Group) => (g.kg >= 1 ? result(g) / g.kg : null), first: "desc" as const },
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

  const activeFilters = Object.entries(filters) as [Exclude<Dim, "month">, string][];
  const sortHead = (label: React.ReactNode, column: keyof typeof columns, className?: string) => (
    <SortableHead
      label={label}
      column={column}
      align={column === "label" ? "left" : "right"}
      sortKey={sortKey}
      sortDir={sortDir}
      onSort={toggle}
      className={className}
    />
  );
  const money = (value: number, className?: string) => (
    <TableCell className={cn("text-right tabular-nums", value < 0 && "text-red-700", className)}>{pesos(value)}</TableCell>
  );
  const colCount = groupBy === "product" ? 11 : 10;
  const sumRow = (s: Sums) => (
    <>
      {money(s.net)}
      {money(gross(s), HIDE_BELOW_SM)}
      {money(s.commission, HIDE_BELOW_LG)}
      {money(contribution(s), HIDE_BELOW_MD)}
      {money(s.route, HIDE_BELOW_LG)}
      {money(result(s))}
      <TableCell className={cn("text-right tabular-nums", result(s) < 0 && "text-red-700")}>
        {s.net ? percent(result(s) / s.net) : "-"}
      </TableCell>
      <TableCell className={cn("text-right tabular-nums", HIDE_BELOW_MD)}>{s.kg ? tonnes(s.kg) : "-"}</TableCell>
      <TableCell className={cn("text-right tabular-nums", HIDE_BELOW_MD, result(s) < 0 && "text-red-700")}>
        {s.kg >= 1 ? formatMoney(result(s) / s.kg) : "-"}
      </TableCell>
    </>
  );

  return (
    <main className="max-w-7xl mx-auto w-full p-4 sm:p-6 flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold text-gray-900">Rentabilidad</h1>
        <p className="text-sm text-gray-500">
          Utilidad por zona, línea, marca, producto y cliente: venta sin IVA, menos costo del ERP, comisiones y gastos
          de ruta. Mismas facturas que Ventas y Comisiones, sin anticipos.
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
        <Button size="sm" variant="outline" className="h-9 sm:h-8" onClick={() => setSetupOpen(true)}>
          <Settings2 className="w-4 h-4" aria-hidden />
          Gastos de ruta
        </Button>
        <Button
          size="sm"
          variant={simOpen ? "default" : "outline"}
          className="h-9 sm:h-8"
          disabled={!data}
          onClick={() => (adjustments.length ? setSimOpen((o) => !o) : addAdjustment({}))}
        >
          <Calculator className="w-4 h-4" aria-hidden />
          Simular
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
        <div className="flex items-center gap-2">
          <span className="text-gray-500">Comisiones</span>
          <Tabs value={commissionMode} onValueChange={(v) => setCommissionMode(v as CommissionMode)}>
            <TabsList className="h-8">
              <TabsTrigger value="posibles" className="text-xs">
                Completas
              </TabsTrigger>
              <TabsTrigger value="pagadas" className="text-xs">
                Pagadas
              </TabsTrigger>
            </TabsList>
          </Tabs>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-gray-500">Gastos de ruta por</span>
          <Tabs value={routeKey} onValueChange={(v) => setRouteKey(v as RouteKey)}>
            <TabsList className="h-8">
              <TabsTrigger value="kg" className="text-xs">
                Kg
              </TabsTrigger>
              <TabsTrigger value="pieza" className="text-xs">
                Pieza
              </TabsTrigger>
            </TabsList>
          </Tabs>
        </div>
        <label className="flex items-center gap-2">
          <Switch checked={importCosts} onCheckedChange={setImportCosts} />
          <span>Sumar costos de importación al costo</span>
        </label>
        <label className="flex items-center gap-2">
          <Switch checked={supplierDiscounts} onCheckedChange={setSupplierDiscounts} />
          <span>Restar notas de crédito de proveedor (Bionat) al costo</span>
        </label>
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
            <Input
              list="rentabilidad-search"
              value={search}
              placeholder="Buscar cliente o producto"
              aria-label="Buscar cliente o producto"
              className="h-9 w-64"
              onChange={(e) => {
                const match = searchOptions.get(e.target.value);
                if (match) {
                  const [dim, id] = match;
                  setFilters((f) => ({ ...f, [dim]: id }));
                  setGroupBy(dim === "client" ? "product" : "client");
                  setSearch("");
                } else {
                  setSearch(e.target.value);
                }
              }}
            />
            <datalist id="rentabilidad-search">
              {[...searchOptions.keys()].map((k) => (
                <option key={k} value={k} />
              ))}
            </datalist>
            {activeFilters
              .filter(([dim]) => dim === "product" || dim === "client")
              .map(([dim, value]) => (
                <span
                  key={dim}
                  className="inline-flex max-w-full items-center gap-1 rounded-full border bg-gray-50 py-1 pl-3 pr-1 text-sm"
                >
                  <span className="truncate">{labelOf(dim, value)}</span>
                  {dim === "product" && (
                    <button
                      type="button"
                      className="shrink-0 text-xs underline hover:text-gray-900"
                      onClick={() => setInvoicesOf(value)}
                    >
                      Facturas
                    </button>
                  )}
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

          {dropped.length > 0 && (
            <div className="flex flex-wrap items-center gap-3 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
              <p className="flex-1 min-w-64">
                <strong>Escenario:</strong> sin vender{" "}
                {dropped.length === 1 ? labelOf("product", dropped[0]) : `${dropped.length} productos`}. Sus ventas,
                costo y comisiones salen; los gastos de ruta (sueldos, vehículos, renta) se quedan y se reparten entre lo
                que sí se vende. Las cifras comparan contra lo real. No se guarda.
                {!scenarioOn && " Calculando…"}
              </p>
              <Button size="sm" variant="outline" onClick={() => setDropped([])}>
                Volver a lo real
              </Button>
            </div>
          )}

          {(simOpen || simOn) && (
            <Card className="border-sky-300">
              <CardHeader className="p-3 sm:p-4">
                <CardTitle className="text-base">Simulación de negociación</CardTitle>
                <CardDescription>
                  Cambie el costo del proveedor, el precio o el volumen de una marca, línea o producto y vea el efecto en
                  todas las cifras. Los gastos de ruta no cambian. No se guarda.
                </CardDescription>
              </CardHeader>
              <div className="flex flex-col gap-3 px-3 pb-3 sm:px-4 sm:pb-4">
                {adjustments.map((a, i) => {
                  const base = adjustmentBase(a);
                  let simulated = emptySums();
                  if (data) {
                    simulated = sumOf(filteredReal.filter((f) => valueOf(f, a.dim, data.products) === a.key));
                  }
                  const effect = result(simulated) - result(base);
                  // With a higher price, the volume it can lose before earning less than today (route costs stay).
                  const perUnit = base.net * (1 + a.price / 100) - base.cost * (1 - a.discount / 100) - base.commission * (1 + a.price / 100);
                  const tolerance = a.price > 0 && contribution(base) > 0 && perUnit > 0 ? 1 - contribution(base) / perUnit : null;
                  return (
                    <div key={i} className="flex flex-col gap-1 rounded-md border p-2">
                      <div className="flex flex-wrap items-center gap-2 text-sm">
                        <select
                          value={a.dim}
                          aria-label="Qué ajustar"
                          onChange={(e) => setAdjustment(i, { dim: e.target.value as Adjustment["dim"], key: "" })}
                          className="h-8 rounded-md border border-input bg-background px-2"
                        >
                          <option value="brand">Marca</option>
                          <option value="category">Línea</option>
                          <option value="product">Producto</option>
                        </select>
                        <select
                          value={a.key}
                          aria-label="Cuál"
                          onChange={(e) => setAdjustment(i, { key: e.target.value })}
                          className="h-8 max-w-72 rounded-md border border-input bg-background px-2"
                        >
                          <option value="">Elegir…</option>
                          {options(a.dim).map((o) => (
                            <option key={o.value} value={o.value}>
                              {o.label}
                            </option>
                          ))}
                        </select>
                        {([
                          ["discount", "Descuento del proveedor"],
                          ["price", "Precio de venta"],
                          ["volume", "Volumen"],
                        ] as const).map(([field, label]) => (
                          <label key={field} className="flex items-center gap-1">
                            <span className="text-gray-500">{label}</span>
                            <Input
                              type="number"
                              step="0.5"
                              aria-label={`${label} en %`}
                              value={a[field] || ""}
                              placeholder="0"
                              onChange={(e) => setAdjustment(i, { [field]: Number(e.target.value) || 0 })}
                              className="h-8 w-20 text-right"
                            />
                            <span className="text-gray-500">%</span>
                          </label>
                        ))}
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-8 px-2 text-gray-500"
                          aria-label="Quitar ajuste"
                          onClick={() => setAdjustments((list) => list.filter((_, j) => j !== i))}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                      {a.key && (
                        <p className="text-xs text-gray-600">
                          Hoy: utilidad neta {formatMoney(result(base))}, contribución {formatMoney(contribution(base))}.
                          {result(base) < 0 && base.cost > 0 && (
                            <>
                              {" "}
                              Para no perder necesitaría{" "}
                              {contribution(base) < 0 && <>{percent(-contribution(base) / base.cost)} de descuento por sí mismo y </>}
                              {percent(-result(base) / base.cost)} para cubrir también su gasto de ruta.
                            </>
                          )}
                          {(a.discount || a.price || a.volume) ? (
                            <>
                              {" "}
                              {adjustments.length > 1 ? "Con todos los ajustes que le tocan" : "Con estos cambios"}:{" "}
                              <strong className={effect < 0 ? "text-red-700" : "text-emerald-700"}>
                                {effect >= 0 ? "+" : ""}
                                {formatMoney(effect)}
                              </strong>{" "}
                              de utilidad neta.
                            </>
                          ) : null}
                          {tolerance !== null && (
                            <> Con +{a.price}% de precio podría perder hasta {percent(tolerance)} del volumen antes de ganar menos que hoy.</>
                          )}
                        </p>
                      )}
                    </div>
                  );
                })}
                <div className="flex flex-wrap gap-2">
                  <Button size="sm" variant="outline" onClick={() => addAdjustment({})}>
                    Agregar ajuste
                  </Button>
                  {adjustments.length > 0 && (
                    <Button size="sm" variant="ghost" onClick={() => (setAdjustments([]), setSimOpen(false))}>
                      Quitar simulación
                    </Button>
                  )}
                </div>
              </div>
            </Card>
          )}

          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <Tile
              label="Ventas"
              value={formatMoney(totals.net)}
              change={versusReal ? change(totals.net, totalsReal.net) : change(totals.net, totalsPrevious.net)}
              changeLabel={versusReal ? "vs real" : undefined}
            />
            <Tile
              label="Utilidad bruta"
              value={formatMoney(gross(totals))}
              sub={totals.net ? `Margen ${percent(gross(totals) / totals.net)}` : undefined}
              change={versusReal ? change(gross(totals), gross(totalsReal)) : change(gross(totals), gross(totalsPrevious))}
              changeLabel={versusReal ? "vs real" : undefined}
            />
            <Tile
              label="Comisiones y gastos de ruta"
              value={formatMoney(totals.commission + totals.route)}
              sub={`${formatMoney(totals.commission)} comisiones · ${formatMoney(totals.route)} ruta`}
            />
            <Tile
              label="Utilidad neta"
              value={formatMoney(result(totals))}
              sub={
                totals.net
                  ? `Margen ${percent(result(totals) / totals.net)}${totals.kg >= 1 ? ` · ${formatMoney(result(totals) / totals.kg)} por kg` : ""}`
                  : undefined
              }
              change={versusReal ? change(result(totals), result(totalsReal)) : change(result(totals), result(totalsPrevious))}
              changeLabel={versusReal ? "vs real" : undefined}
            />
          </div>

          <Card>
            <CardHeader className="p-3 sm:p-4">
              <CardTitle className="text-base">Utilidad por mes</CardTitle>
            </CardHeader>
            <div className="h-56 px-2 pb-3">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chart} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                  <CartesianGrid vertical={false} stroke="#e5e7eb" />
                  <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "#6b7280" }} />
                  <YAxis tickFormatter={compactMoney} tickLine={false} axisLine={false} width={56} tick={{ fontSize: 12, fill: "#6b7280" }} />
                  <Tooltip formatter={(value, name) => [formatMoney(Number(value)), name]} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                  <Legend iconType="plainline" wrapperStyle={{ fontSize: 12 }} />
                  <ReferenceLine y={0} stroke="#94a3b8" />
                  <Line name="Utilidad bruta" dataKey="bruta" stroke={COLOR_GROSS} strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} />
                  <Line name="Utilidad neta" dataKey="neta" stroke={COLOR_NET} strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Card>

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
                <CardDescription>
                  Toque una fila para ver solo {DIMS.find((d) => d.key === groupBy)!.one}.
                  {checkable && " La casilla la quita del escenario para ver cómo quedarían las cifras sin venderla."}
                  {groupBy === "client" && " El nombre abre sus facturas."}
                </CardDescription>
              )}
            </CardHeader>
            <Table className="[&_td]:px-2 [&_td]:whitespace-nowrap [&_th]:px-2">
              <TableHeader>
                <TableRow>
                  {sortHead(DIMS.find((d) => d.key === groupBy)!.label, "label")}
                  {sortHead("Ventas", "net")}
                  {sortHead(<>Utilidad<br />bruta</>, "gross", HIDE_BELOW_SM)}
                  {sortHead("Comisiones", "commission", HIDE_BELOW_LG)}
                  {sortHead("Contribución", "contribution", HIDE_BELOW_MD)}
                  {sortHead(<>Gastos<br />de ruta</>, "route", HIDE_BELOW_LG)}
                  {sortHead(<>Utilidad<br />neta</>, "result")}
                  {sortHead("Margen", "margin")}
                  {sortHead("Peso", "kg", HIDE_BELOW_MD)}
                  {sortHead("Neta / kg", "perKg", HIDE_BELOW_MD)}
                  {groupBy === "product" && <TableHead className="w-px" />}
                </TableRow>
              </TableHeader>
              <TableBody>
                {sorted.length === 0 && <EmptyRow colSpan={colCount}>Sin ventas con estos filtros.</EmptyRow>}
                {sorted.map((g) => (
                  <TableRow
                    key={g.key}
                    className={cn(groupBy !== "month" && !g.dropped && "cursor-pointer", g.dropped && "text-gray-400")}
                    onClick={() => !g.dropped && drill(g)}
                  >
                    <TableCell className={cn("truncate", groupBy === "product" ? "max-w-48" : "max-w-56")} title={g.label}>
                      {checkable && g.key !== NO_PRODUCT && (
                        <input
                          type="checkbox"
                          className="mr-2 h-4 w-4 align-middle accent-slate-900"
                          aria-label={`Incluir ${g.label} en el escenario`}
                          title="Quitar o devolver al escenario (no se guarda)"
                          checked={droppedCount(g.key) === 0}
                          ref={(el) => {
                            if (el) {
                              const n = droppedCount(g.key);
                              el.indeterminate = n > 0 && n < (groupProducts.get(g.key)?.size ?? 0);
                            }
                          }}
                          onClick={(e) => e.stopPropagation()}
                          onChange={() => toggleDrop(g.key)}
                        />
                      )}
                      {groupBy === "client" ? <ClientLink clientId={Number(g.key)} label={g.label} /> : g.label}
                    </TableCell>
                    {sumRow(g)}
                    {groupBy === "product" && (
                      <TableCell className="whitespace-nowrap py-0 text-right">
                        {g.key !== NO_PRODUCT && (
                          <Button
                            size="sm"
                            variant="ghost"
                            className="h-7 w-7 p-0 text-gray-500"
                            aria-label={`Facturas de ${g.label}`}
                            title="Facturas"
                            onClick={(e) => {
                              e.stopPropagation();
                              setInvoicesOf(g.key);
                            }}
                          >
                            <FileText className="h-4 w-4" />
                          </Button>
                        )}
                        {g.key !== NO_PRODUCT && (
                          <Button
                            size="sm"
                            variant="ghost"
                            className="h-7 w-7 p-0 text-gray-500"
                            aria-label={`Excluir ${g.label}`}
                            title="Excluir de la rentabilidad (ventas únicas que distorsionan los números)"
                            onClick={(e) => {
                              e.stopPropagation();
                              if (window.confirm(`¿Dejar fuera "${g.label}"? Se puede volver a incluir después.`)) {
                                setExcluded(g.key, true);
                              }
                            }}
                          >
                            <EyeOff className="h-4 w-4" />
                          </Button>
                        )}
                      </TableCell>
                    )}
                  </TableRow>
                ))}
                {sorted.length > 1 && (
                  <TableRow className="font-medium hover:bg-transparent">
                    <TableCell>Total</TableCell>
                    {sumRow(totals)}
                    {groupBy === "product" && <TableCell />}
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </Card>

          {checkable && breakEven.length > 0 && (
            <Card>
              <CardHeader className="p-3 sm:p-4">
                <CardTitle className="text-base">Qué haría falta para no perder</CardTitle>
                <CardDescription>
                  Descuento del proveedor sobre el costo, sin cambiar el precio de venta. El primero es para que deje de
                  perder por sí mismo; el segundo, para que además cubra su parte de los gastos de ruta.
                </CardDescription>
              </CardHeader>
              <Table className="[&_td]:px-2 [&_td]:whitespace-nowrap [&_th]:px-2">
                <TableHeader>
                  <TableRow>
                    <TableHead>{DIMS.find((d) => d.key === groupBy)!.label}</TableHead>
                    <TableHead className="text-right">Utilidad neta</TableHead>
                    <TableHead className={cn("text-right", HIDE_BELOW_SM)}>Contribución</TableHead>
                    <TableHead className="text-right">
                      Para no
                      <br />
                      perder
                    </TableHead>
                    <TableHead className="text-right">
                      Para cubrir
                      <br />
                      gasto de ruta
                    </TableHead>
                    <TableHead />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {breakEven.map((g) => (
                    <TableRow key={g.key}>
                      <TableCell className="max-w-72 truncate" title={g.label}>
                        {g.label}
                      </TableCell>
                      {money(result(g))}
                      {money(contribution(g), HIDE_BELOW_SM)}
                      <TableCell className="text-right tabular-nums">{g.forContribution ? percent(g.forContribution) : "-"}</TableCell>
                      <TableCell className="text-right tabular-nums">{percent(g.forNet)}</TableCell>
                      <TableCell className="w-px">
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-7"
                          onClick={() =>
                            addAdjustment({
                              dim: groupBy as Adjustment["dim"],
                              key: g.key,
                              discount: Math.ceil(g.forNet * 1000) / 10,
                            })
                          }
                        >
                          Simular
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Card>
          )}

          {pareto && (
            <Card>
              <CardHeader className="p-3 sm:p-4 gap-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <CardTitle className="text-base">Concentración de la contribución</CardTitle>
                  <Tabs value={paretoDim} onValueChange={(v) => setParetoDim(v as "product" | "client")}>
                    <TabsList className="h-8">
                      <TabsTrigger value="product" className="text-xs">
                        Productos
                      </TabsTrigger>
                      <TabsTrigger value="client" className="text-xs">
                        Clientes
                      </TabsTrigger>
                    </TabsList>
                  </Tabs>
                </div>
                <CardDescription>
                  {pareto.to80} de {pareto.count} {paretoDim === "product" ? "productos" : "clientes"} (
                  {percent(pareto.to80 / pareto.count)}) dan el 80% de la contribución.
                  {pareto.losers > 0 &&
                    ` ${pareto.losers} ${paretoDim === "product" ? "productos" : "clientes"} restan ${formatMoney(-pareto.lost)}.`}
                </CardDescription>
              </CardHeader>
              <div className="h-56 px-2 pb-3">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={pareto.points} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
                    <CartesianGrid vertical={false} stroke="#e5e7eb" />
                    <XAxis
                      dataKey="share"
                      type="number"
                      domain={[0, 100]}
                      ticks={[0, 20, 40, 60, 80, 100]}
                      tickFormatter={(v) => `${v}%`}
                      tickLine={false}
                      axisLine={false}
                      tick={{ fontSize: 12, fill: "#6b7280" }}
                    />
                    <YAxis
                      domain={[0, Math.ceil(pareto.peak / 10) * 10]}
                      tickFormatter={(v) => `${v}%`}
                      tickLine={false}
                      axisLine={false}
                      width={44}
                      tick={{ fontSize: 12, fill: "#6b7280" }}
                    />
                    <Tooltip
                      formatter={(value) => [`${Number(value).toFixed(1)}%`, "Contribución acumulada"]}
                      labelFormatter={(v) => `${Number(v).toFixed(0)}% de los ${paretoDim === "product" ? "productos" : "clientes"}`}
                      contentStyle={{ fontSize: 12, borderRadius: 8 }}
                    />
                    <ReferenceLine y={80} stroke="#94a3b8" strokeDasharray="4 4" />
                    <Line dataKey="cumulative" stroke={COLOR_GROSS} strokeWidth={2} dot={false} isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </Card>
          )}

          <Card>
            <CardHeader className="p-3 sm:p-4">
              <CardTitle className="text-base">Gastos de ruta del periodo</CardTitle>
              <CardDescription>
                Todo el periodo, sin filtros. Cada ruta se reparte entre los {routeKey === "kg" ? "kg" : "piezas"} de su
                zona, el almacén entre {routeKey === "kg" ? "todos los kg vendidos" : "todas las piezas vendidas"} y los
                servicios entre las ventas de servicio.
              </CardDescription>
            </CardHeader>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Concepto</TableHead>
                  {Object.keys(POOL_LABELS).map((p) => (
                    <TableHead key={p} className="text-right">
                      {POOL_LABELS[p]}
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {poolComponents.map((c) => (
                  <TableRow key={c}>
                    <TableCell>{c}</TableCell>
                    {Object.keys(POOL_LABELS).map((p) => (
                      <TableCell key={p} className="text-right tabular-nums">
                        {pools[p]?.[c] ? formatMoney(pools[p][c]) : "-"}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
                <TableRow className="font-medium hover:bg-transparent">
                  <TableCell>Total</TableCell>
                  {Object.keys(POOL_LABELS).map((p) => (
                    <TableCell key={p} className="text-right tabular-nums">
                      {formatMoney(Object.values(pools[p] ?? {}).reduce((a, b) => a + b, 0))}
                    </TableCell>
                  ))}
                </TableRow>
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
              Contribución: utilidad bruta menos comisiones, antes de los gastos de ruta. Es lo que se dejaría de ganar
              si no se vendiera; una utilidad neta negativa con contribución positiva solo indica que carga mucho gasto
              compartido.
            </li>
            <li>
              Comisiones completas: la tasa base de cada línea sobre cada factura del periodo, sin descuento por atraso.
              Pagadas: lo que calculó Comisiones, en el mes en que se pagó.
            </li>
            <li>
              Costos de importación: fletes del extranjero, impuestos y derechos de importación, agentes aduanales y
              costo indirecto del periodo ({formatMoney(data.imports.cost)}) entre las compras en moneda extranjera (
              {formatMoney(data.imports.purchases)}): {percent(data.imports.rate)} sobre el costo de los productos
              importados. Importado es lo que se compró en moneda extranjera; lo comprado solo en pesos no lo lleva.
            </li>
            <li>
              Notas de crédito de proveedor: los descuentos sobre compras de Bionat (3% por pronto pago y otros) del mes
              contable, repartidos sobre el costo de lo vendido de Bionat ese mes.
            </li>
            <li>
              Combustible y mantenimiento de los vehículos: del reporte mensual de Contabilidad
              {data.workbook_through ? ` (hasta ${formatMonth(data.workbook_through).toLowerCase()})` : ""}. Los meses
              que aún no están en el reporte usan el libro contable para mantenimiento y gas LP, y los kilómetros del GPS
              {data.gps_since ? ` (desde el ${formatDay(data.gps_since)})` : ""} por rendimiento y precio para el resto
              del combustible.
            </li>
            {unallocated >= 1 && (
              <li>{formatMoney(unallocated)} de gastos de ruta no se repartieron: su zona no tuvo ventas ese mes.</li>
            )}
            <li>
              Los anticipos no cuentan como venta: la factura del anticipo y la nota de crédito que lo aplica se dejan
              fuera, y la factura final cuenta completa en su mes. Por eso algunos meses difieren de Ventas.
            </li>
            <li>
              Las demás notas de crédito no traen producto en el ERP: cada una se reparte entre las partidas de la factura
              a la que se aplicó, en proporción a su importe.
            </li>
            <li>
              Los servicios no tienen costo en el ERP; su costo (técnicos y sus vehículos) entra en los gastos de ruta de
              Servicios.
            </li>
            <li>
              El peso se toma del nombre del producto, del catálogo GEA o de lo capturado en Pesos; el{" "}
              {totals.kg ? percent(estimatedKg / totals.kg) : "0%"} de este peso es estimado.
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

      {setupOpen && <SetupDialog onClose={() => setSetupOpen(false)} onSaved={() => setReload((n) => n + 1)} />}

      {data && invoicesOf && (
        <ProductInvoicesDialog
          title={labelOf("product", invoicesOf)}
          query={new URLSearchParams({
            from,
            to,
            product: invoicesOf,
            ...(filters.client ? { client: filters.client } : {}),
            ...(filters.zone ? { zone: filters.zone } : {}),
          }).toString()}
          onClose={() => setInvoicesOf(null)}
        />
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

interface SetupVehicle {
  id?: number;
  name: string;
  pool: string;
  sheet_name: string;
  maintenance_account: string;
  uses_lp: boolean;
  has_gps?: boolean;
  km_per_liter: number | string | null;
  price_per_liter: number | string | null;
  annual_insurance: number | string;
}

interface Setup {
  pools: { code: string; label: string }[];
  employees: { employee_id: number; pool: string; name: string; position: string; active: boolean }[];
  employee_options: { employee_id: number; name: string; position: string }[];
  vehicles: SetupVehicle[];
  monthly_costs: { id?: number; label: string; pool: string; monthly_amount: number | string }[];
}

// Who and what each route-cost group carries. Edited as a copy and saved whole.
function SetupDialog({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [setup, setSetup] = useState<Setup | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    apiFetch("/api/profitability/setup/")
      .then(async (res) => {
        if (!res.ok) throw new Error("No se pudo cargar la configuración.");
        const json = await res.json();
        if (!cancelled) setSetup(json);
      })
      .catch((err) => !cancelled && setError(err.message));
    return () => {
      cancelled = true;
    };
  }, []);

  const save = async () => {
    if (!setup) return;
    setSaving(true);
    setError(null);
    const res = await apiFetch("/api/profitability/setup/", { method: "PUT", body: JSON.stringify(setup) });
    setSaving(false);
    if (!res.ok) {
      const json = await res.json().catch(() => ({}));
      setError(json.error ?? "No se pudo guardar.");
      return;
    }
    onSaved();
    onClose();
  };

  const update = (change: (s: Setup) => Setup) => setSetup((s) => (s ? change(s) : s));
  const setVehicle = (i: number, patch: Partial<SetupVehicle>) =>
    update((s) => ({ ...s, vehicles: s.vehicles.map((v, j) => (j === i ? { ...v, ...patch } : v)) }));
  const poolSelect = (value: string, onChange: (pool: string) => void, label: string) => (
    <select
      value={value}
      aria-label={label}
      onChange={(e) => onChange(e.target.value)}
      className="h-8 rounded-md border border-input bg-background px-2 text-sm"
    >
      {setup!.pools.map((p) => (
        <option key={p.code} value={p.code}>
          {POOL_LABELS[p.code] ?? p.label}
        </option>
      ))}
    </select>
  );
  const remove = (label: string, onClick: () => void) => (
    <Button size="sm" variant="ghost" className="h-8 px-2 text-gray-500" aria-label={`Quitar ${label}`} onClick={onClick}>
      <Trash2 className="h-4 w-4" />
    </Button>
  );
  const numberInput = (value: number | string | null, onChange: (v: string) => void, label: string, width = "w-24") => (
    <Input
      type="number"
      inputMode="decimal"
      min={0}
      step="any"
      aria-label={label}
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value)}
      className={cn("h-8 text-right", width)}
    />
  );
  const available = setup?.employee_options.filter((o) => !setup.employees.some((e) => e.employee_id === o.employee_id));

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-5xl max-h-[90vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>Gastos de ruta: configuración</DialogTitle>
        </DialogHeader>
        {!setup && !error && <p className="text-sm text-gray-500">Cargando…</p>}
        {setup && (
          <div className="flex flex-col gap-6 overflow-y-auto pr-1">
            <section className="flex flex-col gap-2">
              <h3 className="text-sm font-semibold">Personal</h3>
              <p className="text-xs text-gray-500">Su nómina (percepciones y cuotas patronales, sin PTU) va al grupo elegido.</p>
              <Table>
                <TableBody>
                  {setup.employees.map((e, i) => (
                    <TableRow key={e.employee_id}>
                      <TableCell>
                        {e.name || `Empleado ${e.employee_id}`}
                        <span className="ml-2 text-xs text-gray-500">
                          {e.position}
                          {!e.active && " · baja"}
                        </span>
                      </TableCell>
                      <TableCell className="w-48">
                        {poolSelect(
                          e.pool,
                          (pool) => update((s) => ({ ...s, employees: s.employees.map((x, j) => (j === i ? { ...x, pool } : x)) })),
                          `Grupo de ${e.name}`,
                        )}
                      </TableCell>
                      <TableCell className="w-px">
                        {remove(e.name, () => update((s) => ({ ...s, employees: s.employees.filter((_, j) => j !== i) })))}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              {available && available.length > 0 && (
                <select
                  value=""
                  aria-label="Agregar empleado"
                  onChange={(e) => {
                    const o = available.find((x) => String(x.employee_id) === e.target.value);
                    if (o) update((s) => ({ ...s, employees: [...s.employees, { ...o, pool: "ZONA1", active: true }] }));
                  }}
                  className="h-8 w-72 rounded-md border border-input bg-background px-2 text-sm"
                >
                  <option value="">Agregar empleado…</option>
                  {available.map((o) => (
                    <option key={o.employee_id} value={o.employee_id}>
                      {o.name} ({o.position})
                    </option>
                  ))}
                </select>
              )}
            </section>

            <section className="flex flex-col gap-2">
              <h3 className="text-sm font-semibold">Vehículos</h3>
              <p className="text-xs text-gray-500">
                Combustible y mantenimiento salen del reporte mensual de Contabilidad (nombre en el reporte). Para los
                meses que aún no están ahí: mantenimiento de su cuenta contable, y combustible de la cuenta de gas LP o
                de los km del GPS entre el rendimiento, por el precio por litro. El seguro se reparte en 12 meses.
              </p>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Vehículo</TableHead>
                    <TableHead>Grupo</TableHead>
                    <TableHead>Nombre en el reporte</TableHead>
                    <TableHead>Cuenta de mantenimiento</TableHead>
                    <TableHead>Gas LP</TableHead>
                    <TableHead className="text-right">Km/litro</TableHead>
                    <TableHead className="text-right">$/litro</TableHead>
                    <TableHead className="text-right">Seguro anual</TableHead>
                    <TableHead />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {setup.vehicles.map((v, i) => (
                    <TableRow key={v.id ?? `new-${i}`}>
                      <TableCell>
                        <Input
                          value={v.name}
                          aria-label="Nombre del vehículo"
                          onChange={(e) => setVehicle(i, { name: e.target.value })}
                          className="h-8 w-36"
                        />
                        <span className="text-xs text-gray-500">{v.has_gps ? "Con GPS" : "Sin GPS"}</span>
                      </TableCell>
                      <TableCell>{poolSelect(v.pool, (pool) => setVehicle(i, { pool }), `Grupo de ${v.name}`)}</TableCell>
                      <TableCell>
                        <Input
                          value={v.sheet_name}
                          aria-label={`Nombre en el reporte de ${v.name}`}
                          onChange={(e) => setVehicle(i, { sheet_name: e.target.value })}
                          className="h-8 w-28"
                        />
                      </TableCell>
                      <TableCell>
                        <Input
                          value={v.maintenance_account}
                          aria-label={`Cuenta de mantenimiento de ${v.name}`}
                          onChange={(e) => setVehicle(i, { maintenance_account: e.target.value })}
                          className="h-8 w-28"
                        />
                      </TableCell>
                      <TableCell>
                        <Switch
                          checked={v.uses_lp}
                          aria-label={`${v.name} usa gas LP`}
                          onCheckedChange={(uses_lp) => setVehicle(i, { uses_lp })}
                        />
                      </TableCell>
                      <TableCell className="text-right">
                        {numberInput(v.km_per_liter, (x) => setVehicle(i, { km_per_liter: x }), `Km por litro de ${v.name}`, "w-20")}
                      </TableCell>
                      <TableCell className="text-right">
                        {numberInput(v.price_per_liter, (x) => setVehicle(i, { price_per_liter: x }), `Precio por litro de ${v.name}`, "w-20")}
                      </TableCell>
                      <TableCell className="text-right">
                        {numberInput(v.annual_insurance, (x) => setVehicle(i, { annual_insurance: x }), `Seguro anual de ${v.name}`, "w-28")}
                      </TableCell>
                      <TableCell className="w-px">
                        {remove(v.name, () => update((s) => ({ ...s, vehicles: s.vehicles.filter((_, j) => j !== i) })))}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <Button
                size="sm"
                variant="outline"
                className="self-start"
                onClick={() =>
                  update((s) => ({
                    ...s,
                    vehicles: [
                      ...s.vehicles,
                      {
                        name: "", pool: "ZONA1", sheet_name: "", maintenance_account: "", uses_lp: false,
                        km_per_liter: null, price_per_liter: null, annual_insurance: 0,
                      },
                    ],
                  }))
                }
              >
                Agregar vehículo
              </Button>
            </section>

            <section className="flex flex-col gap-2">
              <h3 className="text-sm font-semibold">Gastos fijos mensuales</h3>
              <p className="text-xs text-gray-500">Montos que no están en el libro contable, como la renta de la bodega.</p>
              <Table>
                <TableBody>
                  {setup.monthly_costs.map((c, i) => (
                    <TableRow key={c.id ?? `new-${i}`}>
                      <TableCell>
                        <Input
                          value={c.label}
                          aria-label="Concepto"
                          onChange={(e) =>
                            update((s) => ({
                              ...s,
                              monthly_costs: s.monthly_costs.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)),
                            }))
                          }
                          className="h-8 w-56"
                        />
                      </TableCell>
                      <TableCell>
                        {poolSelect(
                          c.pool,
                          (pool) => update((s) => ({ ...s, monthly_costs: s.monthly_costs.map((x, j) => (j === i ? { ...x, pool } : x)) })),
                          `Grupo de ${c.label}`,
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        {numberInput(
                          c.monthly_amount,
                          (monthly_amount) =>
                            update((s) => ({ ...s, monthly_costs: s.monthly_costs.map((x, j) => (j === i ? { ...x, monthly_amount } : x)) })),
                          `Monto mensual de ${c.label}`,
                          "w-28",
                        )}
                      </TableCell>
                      <TableCell className="w-px">
                        {remove(c.label, () => update((s) => ({ ...s, monthly_costs: s.monthly_costs.filter((_, j) => j !== i) })))}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <Button
                size="sm"
                variant="outline"
                className="self-start"
                onClick={() =>
                  update((s) => ({ ...s, monthly_costs: [...s.monthly_costs, { label: "", pool: "ALMACEN", monthly_amount: 0 }] }))
                }
              >
                Agregar gasto fijo
              </Button>
            </section>
          </div>
        )}
        {error && <p className="text-sm text-red-700">{error}</p>}
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button onClick={save} disabled={!setup || saving}>
            Guardar
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

interface InvoiceLine {
  invoice_id: number;
  folio: string;
  return: boolean;
  date: string;
  zone: string;
  client_id: number;
  client: string;
  units: number;
  net: number;
  cost: number;
}

// The invoice and return lines behind a product's numbers, for the period and the zone/client filters.
function ProductInvoicesDialog({ title, query, onClose }: { title: string; query: string; onClose: () => void }) {
  const [lines, setLines] = useState<InvoiceLine[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiFetch(`/api/profitability/invoices/?${query}`)
      .then(async (res) => {
        if (!res.ok) throw new Error("No se pudieron cargar las facturas.");
        const json = await res.json();
        if (!cancelled) setLines(json);
      })
      .catch((err) => !cancelled && setError(err.message));
    return () => {
      cancelled = true;
    };
  }, [query]);

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-4xl max-h-[85vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="pr-6">{title}</DialogTitle>
        </DialogHeader>
        {error && <p className="text-sm text-red-700">{error}</p>}
        {!lines && !error && <p className="text-sm text-gray-500">Cargando…</p>}
        {lines && (
          <div className="overflow-y-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Folio</TableHead>
                  <TableHead>Fecha</TableHead>
                  <TableHead>Cliente</TableHead>
                  <TableHead className={HIDE_BELOW_MD}>Zona</TableHead>
                  <TableHead className="text-right">Unidades</TableHead>
                  <TableHead className="text-right">Venta</TableHead>
                  <TableHead className={cn("text-right", HIDE_BELOW_SM)}>Utilidad bruta</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {lines.length === 0 && <EmptyRow colSpan={7}>Sin facturas en el periodo.</EmptyRow>}
                {lines.map((l) => (
                  <TableRow key={l.invoice_id}>
                    <TableCell className="whitespace-nowrap">
                      <InvoiceLink invoiceId={l.invoice_id} label={l.folio} />
                      {l.return && <span className="ml-1 text-xs text-gray-500">(devolución)</span>}
                    </TableCell>
                    <TableCell className="whitespace-nowrap">{formatDay(l.date)}</TableCell>
                    <TableCell className="max-w-56 truncate">
                      <ClientLink clientId={l.client_id} label={l.client} />
                    </TableCell>
                    <TableCell className={HIDE_BELOW_MD}>{zoneLabel(l.zone)}</TableCell>
                    <TableCell className="text-right tabular-nums">{l.units.toLocaleString("es-MX")}</TableCell>
                    <TableCell className="text-right tabular-nums">{formatMoney(l.net)}</TableCell>
                    <TableCell className={cn("text-right tabular-nums", HIDE_BELOW_SM, l.net - l.cost < 0 && "text-red-700")}>
                      {formatMoney(l.net - l.cost)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <p className="mt-2 text-xs text-gray-500">
              Las notas de crédito que se repartieron sobre este producto no aparecen aquí; se ven al abrir cada factura.
            </p>
          </div>
        )}
      </DialogContent>
    </Dialog>
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

