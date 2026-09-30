"use client";

import { useMemo, useState } from "react";
import { ChevronDown } from "lucide-react";
import { cn, plural } from "@/lib/utils";
import ProductCard from "@/components/catalog/ProductCard";
import CatalogFilters, {
  EMPTY_FILTERS,
  Filters,
  hasPrice,
  matches,
  normalize,
  priceBreaks,
} from "@/components/catalog/CatalogFilters";
import { useSearchQuery } from "@/hooks/use-search-query";
import { Product } from "@/types/api";

type SortMode = "relevance" | "best-sellers" | "price-asc" | "price-desc";

export const SORT_OPTIONS: { value: SortMode; label: string }[] = [
  { value: "relevance", label: "Más relevantes" },
  { value: "best-sellers", label: "Más vendidos" },
  { value: "price-asc", label: "Menor precio" },
  { value: "price-desc", label: "Mayor precio" },
];

export default function CatalogView({ products }: { products: Product[] }) {
  const { query } = useSearchQuery();
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [sortMode, setSortMode] = useState<SortMode>("relevance");
  // Phones start with the filters folded away so products show first.
  const [filtersOpen, setFiltersOpen] = useState(false);

  const normalizedQuery = normalize(query.trim());
  // Ranges come from the whole catalog so they don't jump while filtering.
  const breaks = useMemo(() => priceBreaks(products), [products]);

  const filtered = useMemo(() => {
    let result = products.filter((product) => matches(product, filters, normalizedQuery));

    // Relevance with a search: exact code, then name starting with it, then the rest.
    const relevance = (p: Product) => {
      if (!normalizedQuery) return 0;
      if (normalize(p.CCODIGOPRODUCTO) === normalizedQuery) return 0;
      if (normalize(p.CNOMBREPRODUCTO).startsWith(normalizedQuery)) return 1;
      return 2;
    };
    const direction = sortMode === "price-desc" ? -1 : 1;
    // Every sort puts $0 products after the priced ones; ties keep the ERP order.
    result = [...result].sort((a, b) => {
      const priced = Number(!hasPrice(a)) - Number(!hasPrice(b));
      if (priced) return priced;
      if (sortMode === "best-sellers") {
        return (a.sold_rank ?? Infinity) - (b.sold_rank ?? Infinity) || relevance(a) - relevance(b);
      }
      if (sortMode === "price-asc" || sortMode === "price-desc") {
        // Hidden prices have no value to compare - they go after the shown ones.
        if (a.CPRECIO1 === null || b.CPRECIO1 === null) {
          return Number(a.CPRECIO1 === null) - Number(b.CPRECIO1 === null);
        }
        return (a.CPRECIO1 - b.CPRECIO1) * direction;
      }
      return relevance(a) - relevance(b);
    });

    return result;
  }, [products, filters, sortMode, normalizedQuery]);

  const activeFilters =
    filters.category.size + filters.line.size + filters.brand.size +
    Number(filters.inStock) + Number(filters.withPrice) + Number(Boolean(filters.min || filters.max));

  return (
    <main className="flex flex-col md:flex-row max-w-7xl mx-auto w-full gap-4 md:gap-8 p-4 sm:p-6">
      <button
        type="button"
        onClick={() => setFiltersOpen((o) => !o)}
        aria-expanded={filtersOpen}
        className="md:hidden flex items-center justify-between rounded-lg border border-gray-200 bg-white px-4 py-2.5 text-sm font-medium text-gray-700"
      >
        <span>
          Filtros
          {activeFilters > 0 && <span className="ml-1.5 text-gray-400">({activeFilters})</span>}
        </span>
        <ChevronDown className={cn("w-4 h-4 transition-transform", filtersOpen && "rotate-180")} />
      </button>
      <CatalogFilters
        className={filtersOpen ? "block" : "hidden md:block"}
        products={products}
        breaks={breaks}
        filters={filters}
        query={normalizedQuery}
        resultCount={filtered.length}
        onChange={setFilters}
      />

      <div className="flex-1 flex flex-col">
        {/* The count lives in the filter column; phones fold that away. */}
        <div className="mb-4 flex items-center justify-between gap-3 md:justify-end">
          <span className="whitespace-nowrap text-sm text-gray-500 md:hidden">
            {plural(filtered.length, "resultado", "resultados")}
          </span>
          <label className="flex items-center gap-2 text-sm text-gray-600">
            <span className="whitespace-nowrap">Ordenar por</span>
            <select
              value={sortMode}
              onChange={(e) => setSortMode(e.target.value as SortMode)}
              className="rounded border-none bg-transparent py-1 pl-1 pr-7 text-sm font-medium text-blue-600 focus:ring-2 focus:ring-blue-500"
            >
              {SORT_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        {filtered.length > 0 ? (
          <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-3 xl:grid-cols-4">
            {filtered.map((product) => (
              <ProductCard key={product.CIDPRODUCTO} product={product} />
            ))}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-gray-300 bg-white py-8 text-center">
            <p className="text-sm text-gray-500">Sin productos que mostrar.</p>
          </div>
        )}
      </div>
    </main>
  );
}
