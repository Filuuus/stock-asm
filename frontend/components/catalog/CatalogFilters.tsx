"use client";

import { useState } from "react";
import { X } from "lucide-react";
import { cn, formatMoney, plural } from "@/lib/utils";
import { Product } from "@/types/api";

// Customer-facing names for the commission categories (api/services.py).
export const CATEGORY_LABELS: Record<string, string> = {
  R: "Refacciones",
  R_CHEM: "Químicos",
  R_NW: "Tapetes y pernos",
  R_FAN: "Ventiladores",
  B: "Bionat",
  B_MIPRO: "Mipro",
  B_BOVI: "Bovifit",
  S: "Servicios",
};

export interface Filters {
  category: Set<string>;
  line: Set<string>;
  brand: Set<string>;
  inStock: boolean;
  withPrice: boolean;
  min: string;
  max: string;
}

export type FilterGroup = "category" | "line" | "brand" | "inStock" | "withPrice" | "price";
type SetGroup = "category" | "line" | "brand";

export const EMPTY_FILTERS: Filters = {
  category: new Set(),
  line: new Set(),
  brand: new Set(),
  inStock: false,
  withPrice: false,
  min: "",
  max: "",
};

export function normalize(text: string) {
  return text
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();
}

// A hidden price counts as priced, so neither this filter nor the sort
// reveals which hidden prices are $0.
export const hasPrice = (p: Product) => p.CPRECIO1 === null || p.CPRECIO1 > 0;

// Line names are uppercase in the ERP; show them as a sentence.
export const lineLabel = (line: string) => line.charAt(0) + line.slice(1).toLowerCase();

// Does the product pass every filter except `skip`? Skipping a group is how
// each group's counts show what picking that option would give.
export function matches(p: Product, f: Filters, query: string, skip?: FilterGroup) {
  if (skip !== "category" && f.category.size && !f.category.has(p.category)) return false;
  if (skip !== "line" && f.line.size && !(p.line && f.line.has(p.line))) return false;
  if (skip !== "brand" && f.brand.size && !(p.brand && f.brand.has(p.brand))) return false;
  if (skip !== "inStock" && f.inStock && !p.in_stock) return false;
  if (skip !== "withPrice" && f.withPrice && !hasPrice(p)) return false;
  if (skip !== "price" && (f.min || f.max)) {
    // A hidden price can't be checked against a range - leave it out.
    if (p.CPRECIO1 === null) return false;
    if (f.min && p.CPRECIO1 < parseFloat(f.min)) return false;
    if (f.max && p.CPRECIO1 > parseFloat(f.max)) return false;
  }
  if (query && !normalize(`${p.CNOMBREPRODUCTO} ${p.CCODIGOPRODUCTO}`).includes(query)) return false;
  return true;
}

// Three ranges splitting the visible prices into thirds, rounded to two
// significant digits ("Hasta $450", "$450 a $2,300", "Más de $2,300").
export function priceBreaks(products: Product[]): [number, number] | null {
  const prices = products
    .map((p) => p.CPRECIO1)
    .filter((v): v is number => v !== null && v > 0)
    .sort((a, b) => a - b);
  if (prices.length < 6) return null;
  const round = (v: number) => Number(v.toPrecision(2));
  const low = round(prices[Math.floor(prices.length / 3)]);
  const high = round(prices[Math.floor((prices.length * 2) / 3)]);
  return low < high ? [low, high] : null;
}

interface Option {
  value: string;
  label: string;
  count: number;
}

function countBy(products: Product[], key: (p: Product) => string | null, label = (v: string) => v) {
  const counts = new Map<string, number>();
  for (const p of products) {
    const v = key(p);
    if (v) counts.set(v, (counts.get(v) ?? 0) + 1);
  }
  return [...counts]
    .map(([value, count]) => ({ value, label: label(value), count }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label, "es"));
}

const VISIBLE_OPTIONS = 5;

function FacetGroup({
  title,
  options,
  selected,
  onToggle,
}: {
  title: string;
  options: Option[];
  selected: Set<string>;
  onToggle: (value: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  // Options with no results are hidden unless they're checked.
  const shown = options.filter((o) => o.count > 0 || selected.has(o.value));
  if (shown.length === 0) return null;
  const visible = expanded ? shown : shown.slice(0, VISIBLE_OPTIONS);
  return (
    <section>
      <h3 className="mb-2 text-sm font-semibold text-gray-900">{title}</h3>
      <ul className="space-y-1.5 text-sm text-gray-600">
        {visible.map((o) => (
          <li key={o.value}>
            <label className="flex cursor-pointer items-start gap-2">
              <input
                type="checkbox"
                checked={selected.has(o.value)}
                onChange={() => onToggle(o.value)}
                className="mt-0.5 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              />
              <span className="flex-1">
                {o.label} <span className="text-gray-400">({o.count})</span>
              </span>
            </label>
          </li>
        ))}
      </ul>
      {shown.length > VISIBLE_OPTIONS && (
        <button
          type="button"
          onClick={() => setExpanded((e) => !e)}
          className="mt-2 text-sm text-blue-600 hover:underline"
        >
          {expanded ? "Ver menos" : "Ver más"}
        </button>
      )}
    </section>
  );
}

function Toggle({
  label,
  count,
  checked,
  onChange,
}: {
  label: string;
  count: number;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-center gap-2 text-sm text-gray-600">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
      />
      <span>
        {label} <span className="text-gray-400">({count})</span>
      </span>
    </label>
  );
}

function PriceGroup({
  products,
  breaks,
  filters,
  onChange,
  children,
}: {
  products: Product[];
  breaks: [number, number] | null;
  filters: Filters;
  onChange: (min: string, max: string) => void;
  children: React.ReactNode;
}) {
  const [min, setMin] = useState(filters.min);
  const [max, setMax] = useState(filters.max);
  const [prevApplied, setPrevApplied] = useState([filters.min, filters.max]);
  // Keep the boxes in sync when a range link or chip changes the filter.
  if (prevApplied[0] !== filters.min || prevApplied[1] !== filters.max) {
    setPrevApplied([filters.min, filters.max]);
    setMin(filters.min);
    setMax(filters.max);
  }

  const count = (lo: number | null, hi: number | null) =>
    products.filter(
      (p) => p.CPRECIO1 !== null && p.CPRECIO1 > 0 && (lo === null || p.CPRECIO1 >= lo) && (hi === null || p.CPRECIO1 <= hi)
    ).length;
  const ranges = breaks
    ? [
        { label: `Hasta ${formatMoney(breaks[0])}`, lo: null, hi: breaks[0] },
        { label: `${formatMoney(breaks[0])} a ${formatMoney(breaks[1])}`, lo: breaks[0], hi: breaks[1] },
        { label: `Más de ${formatMoney(breaks[1])}`, lo: breaks[1], hi: null },
      ]
    : [];

  return (
    <section>
      <h3 className="mb-2 text-sm font-semibold text-gray-900">Precio</h3>
      {children}
      <ul className="mt-1.5 space-y-1.5 text-sm">
        {ranges.map((r) => {
          const n = count(r.lo, r.hi);
          if (n === 0) return null;
          return (
            <li key={r.label}>
              <button
                type="button"
                onClick={() => onChange(r.lo === null ? "" : String(r.lo), r.hi === null ? "" : String(r.hi))}
                className="text-left text-gray-600 hover:text-blue-600"
              >
                {r.label} <span className="text-gray-400">({n})</span>
              </button>
            </li>
          );
        })}
      </ul>
      <form
        className="mt-3 flex items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          onChange(min, max);
        }}
      >
        <input
          type="number"
          min="0"
          inputMode="decimal"
          value={min}
          onChange={(e) => setMin(e.target.value)}
          placeholder="Mínimo"
          aria-label="Precio mínimo"
          className="w-full min-w-0 rounded border border-gray-300 px-2 py-1.5 text-sm text-gray-700 focus:border-blue-500 focus:outline-none"
        />
        <span className="text-gray-400">-</span>
        <input
          type="number"
          min="0"
          inputMode="decimal"
          value={max}
          onChange={(e) => setMax(e.target.value)}
          placeholder="Máximo"
          aria-label="Precio máximo"
          className="w-full min-w-0 rounded border border-gray-300 px-2 py-1.5 text-sm text-gray-700 focus:border-blue-500 focus:outline-none"
        />
        <button
          type="submit"
          aria-label="Aplicar precio"
          className="shrink-0 rounded border border-gray-300 px-2 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
        >
          ›
        </button>
      </form>
    </section>
  );
}

interface CatalogFiltersProps {
  products: Product[];
  breaks: [number, number] | null;
  filters: Filters;
  query: string;
  resultCount: number;
  onChange: (filters: Filters) => void;
  className?: string;
}

export default function CatalogFilters({
  products,
  breaks,
  filters,
  query,
  resultCount,
  onChange,
  className,
}: CatalogFiltersProps) {
  // Each group counts over the products that pass every OTHER filter.
  const pool = (skip: FilterGroup) => products.filter((p) => matches(p, filters, query, skip));

  const toggle = (group: SetGroup, value: string) => {
    const next = new Set(filters[group]);
    if (next.has(value)) next.delete(value);
    else next.add(value);
    const updated = { ...filters, [group]: next };
    if (group === "category") {
      // Drop picked lines that no longer belong to any picked category.
      const lines = new Set(
        products.filter((p) => next.size === 0 || next.has(p.category)).map((p) => p.line)
      );
      updated.line = new Set([...filters.line].filter((l) => next.size > 0 && lines.has(l)));
    }
    onChange(updated);
  };

  const chips: { label: string; remove: () => void }[] = [
    ...[...filters.category].map((v) => ({ label: CATEGORY_LABELS[v] ?? v, remove: () => toggle("category", v) })),
    ...[...filters.line].map((v) => ({ label: lineLabel(v), remove: () => toggle("line", v) })),
    ...[...filters.brand].map((v) => ({ label: v, remove: () => toggle("brand", v) })),
    ...(filters.inStock ? [{ label: "Disponible", remove: () => onChange({ ...filters, inStock: false }) }] : []),
    ...(filters.withPrice ? [{ label: "Con precio", remove: () => onChange({ ...filters, withPrice: false }) }] : []),
    ...(filters.min || filters.max
      ? [
          {
            label: filters.min && filters.max
              ? `${formatMoney(+filters.min)} a ${formatMoney(+filters.max)}`
              : filters.min
                ? `Desde ${formatMoney(+filters.min)}`
                : `Hasta ${formatMoney(+filters.max)}`,
            remove: () => onChange({ ...filters, min: "", max: "" }),
          },
        ]
      : []),
  ];

  const inStockCount = pool("inStock").filter((p) => p.in_stock).length;
  const withPriceCount = pool("withPrice").filter(hasPrice).length;

  return (
    <aside className={cn("w-full flex-shrink-0 space-y-6 md:w-64", className)}>
      <div>
        <p className="text-sm text-gray-500">{plural(resultCount, "resultado", "resultados")}</p>
        {chips.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {chips.map((c, i) => (
              <button
                key={`${i}-${c.label}`}
                type="button"
                onClick={c.remove}
                aria-label={`Quitar filtro ${c.label}`}
                className="inline-flex max-w-full items-center gap-1 rounded-full bg-gray-100 px-3 py-1 text-xs text-gray-700 hover:bg-gray-200"
              >
                <span className="truncate">{c.label}</span>
                <X className="h-3 w-3 shrink-0" />
              </button>
            ))}
            <button
              type="button"
              onClick={() => onChange(EMPTY_FILTERS)}
              className="text-xs text-blue-600 hover:underline"
            >
              Limpiar filtros
            </button>
          </div>
        )}
      </div>

      <FacetGroup
        title="Categoría"
        options={countBy(pool("category"), (p) => p.category, (v) => CATEGORY_LABELS[v] ?? v)}
        selected={filters.category}
        onToggle={(v) => toggle("category", v)}
      />
      {/* Línea is the sub-level: it appears once a category is picked. */}
      {filters.category.size > 0 && (
        <FacetGroup
          title="Línea"
          options={countBy(pool("line"), (p) => p.line, lineLabel)}
          selected={filters.line}
          onToggle={(v) => toggle("line", v)}
        />
      )}
      <FacetGroup
        title="Marca"
        options={countBy(pool("brand"), (p) => p.brand)}
        selected={filters.brand}
        onToggle={(v) => toggle("brand", v)}
      />
      <section>
        <h3 className="mb-2 text-sm font-semibold text-gray-900">Disponibilidad</h3>
        <Toggle
          label="Disponible"
          count={inStockCount}
          checked={filters.inStock}
          onChange={(inStock) => onChange({ ...filters, inStock })}
        />
      </section>
      <PriceGroup
        products={pool("price")}
        breaks={breaks}
        filters={filters}
        onChange={(min, max) => onChange({ ...filters, min, max })}
      >
        <Toggle
          label="Con precio"
          count={withPriceCount}
          checked={filters.withPrice}
          onChange={(withPrice) => onChange({ ...filters, withPrice })}
        />
      </PriceGroup>
    </aside>
  );
}
