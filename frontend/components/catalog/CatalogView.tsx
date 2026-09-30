"use client";

import { useMemo, useState } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import ProductCard from "@/components/catalog/ProductCard";
import CatalogFilters, {
  EMPTY_FILTERS,
  Filters,
  matches,
  normalize,
  priceBreaks,
} from "@/components/catalog/CatalogFilters";
import { useSearchQuery } from "@/hooks/use-search-query";
import { Product } from "@/types/api";

type SortMode = "relevance" | "price-asc" | "price-desc";

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

    if (sortMode === "price-asc" || sortMode === "price-desc") {
      // Hidden prices (null) always sort last, regardless of direction -
      // there's no real value to compare them by.
      const direction = sortMode === "price-asc" ? 1 : -1;
      result = [...result].sort((a, b) => {
        if (a.CPRECIO1 === null) return b.CPRECIO1 === null ? 0 : 1;
        if (b.CPRECIO1 === null) return -1;
        return (a.CPRECIO1 - b.CPRECIO1) * direction;
      });
    } else if (normalizedQuery) {
      // Relevance: exact code match, then name starting with the query, then the rest.
      const rank = (product: Product) => {
        const code = normalize(product.CCODIGOPRODUCTO);
        const name = normalize(product.CNOMBREPRODUCTO);
        if (code === normalizedQuery) return 0;
        if (name.startsWith(normalizedQuery)) return 1;
        return 2;
      };
      result = [...result].sort((a, b) => rank(a) - rank(b));
    }

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
        <div className="flex flex-wrap items-center justify-between gap-3 mb-6 pb-4 border-b border-gray-200">
          <span className="text-sm text-gray-500 font-medium">
            Mostrando {filtered.length} productos
          </span>
          <div className="flex items-center space-x-2 text-sm text-gray-600">
            <span className="whitespace-nowrap">Ordenar por:</span>
            <select
              value={sortMode}
              onChange={(e) => setSortMode(e.target.value as SortMode)}
              className="border border-gray-300 rounded px-2 py-1 bg-white focus:outline-none"
            >
              <option value="relevance">Relevancia</option>
              <option value="price-asc">Precio: Menor a Mayor</option>
              <option value="price-desc">Precio: Mayor a Menor</option>
            </select>
          </div>
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
