"use client";

import { useEffect, useMemo, useState } from "react";
import { ArrowUpDown, SlidersHorizontal } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { cn, plural } from "@/lib/utils";
import ProductCard from "@/components/catalog/ProductCard";
import GeaPartResults from "@/components/catalog/GeaPartResults";
import CatalogFilters, {
  Filters,
  filtersFromParams,
  filtersToParams,
  hasPrice,
  matches,
  normalize,
  priceBreaks,
} from "@/components/catalog/CatalogFilters";
import { useSearchQuery } from "@/hooks/use-search-query";
import { Product } from "@/types/api";

type SortMode = "relevance" | "best-sellers" | "price-asc" | "price-desc";

const PANEL_BUTTON =
  "inline-flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-700";

export const SORT_OPTIONS: { value: SortMode; label: string }[] = [
  { value: "relevance", label: "Más relevantes" },
  { value: "best-sellers", label: "Más vendidos" },
  { value: "price-asc", label: "Menor precio" },
  { value: "price-desc", label: "Mayor precio" },
];

const SORT_VALUES = SORT_OPTIONS.map((o) => o.value);

// Remembered per tab so "‹ Catálogo" on a product page returns to the same
// filtered list and scroll position.
export const CATALOG_URL_KEY = "catalog-url";
export const CATALOG_SCROLL_KEY = "catalog-scroll";
export const CATALOG_RESTORE_KEY = "catalog-restore";

function session(action: (s: Storage) => void) {
  try {
    action(sessionStorage);
  } catch {
    // storage blocked: the catalog simply opens at the top
  }
}

export default function CatalogView({ products }: { products: Product[] }) {
  const { query } = useSearchQuery();
  // Start from the current URL - also when coming back to the catalog, where
  // Next reuses the page as first rendered (without these filters).
  const searchParams = useSearchParams();
  const [filters, setFilters] = useState<Filters>(() => filtersFromParams(new URLSearchParams(searchParams)));
  const [sortMode, setSortMode] = useState<SortMode>(() => {
    const orden = searchParams.get("orden") as SortMode | null;
    return orden && SORT_VALUES.includes(orden) ? orden : "relevance";
  });

  // Keep the URL in step with the filters (no reload, no new history entry).
  useEffect(() => {
    const params = filtersToParams(filters);
    if (sortMode !== "relevance") params.set("orden", sortMode);
    const url = params.size ? `/?${params}` : "/";
    if (url !== window.location.pathname + window.location.search) window.history.replaceState(null, "", url);
    session((s) => s.setItem(CATALOG_URL_KEY, url));
  }, [filters, sortMode]);

  // Arriving from a product's "‹ Catálogo" link: back to where the user was.
  useEffect(() => {
    session((s) => {
      if (!s.getItem(CATALOG_RESTORE_KEY)) return;
      s.removeItem(CATALOG_RESTORE_KEY);
      const y = Number(s.getItem(CATALOG_SCROLL_KEY));
      if (y) requestAnimationFrame(() => window.scrollTo(0, y));
    });
  }, []);
  // Phones only: the filter and sort side panels.
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [sortOpen, setSortOpen] = useState(false);

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

  const filterProps = {
    products,
    breaks,
    filters,
    query: normalizedQuery,
    resultCount: filtered.length,
    onChange: setFilters,
  };

  return (
    <main className="flex flex-col md:flex-row max-w-7xl mx-auto w-full gap-4 md:gap-8 p-4 sm:p-6">
      <CatalogFilters className="hidden md:block" {...filterProps} />

      <div className="flex-1 flex flex-col">
        {/* Phones: count plus buttons that open the filters and the sort as side panels. */}
        <div className="mb-4 flex items-center justify-between gap-3 md:hidden">
          <span className="whitespace-nowrap text-sm text-gray-500">
            {plural(filtered.length, "resultado", "resultados")}
          </span>
          <div className="flex gap-2">
            <Sheet open={sortOpen} onOpenChange={setSortOpen}>
              <SheetTrigger asChild>
                <button type="button" className={PANEL_BUTTON}>
                  <ArrowUpDown className="h-4 w-4" />
                  Ordenar
                </button>
              </SheetTrigger>
              <SheetContent side="right" className="w-[85%]">
                <SheetTitle className="mb-4">Ordenar por</SheetTitle>
                <div className="space-y-1">
                  {SORT_OPTIONS.map((o) => (
                    <button
                      key={o.value}
                      type="button"
                      onClick={() => {
                        setSortMode(o.value);
                        setSortOpen(false);
                      }}
                      className={cn(
                        "block w-full rounded px-3 py-2.5 text-left text-sm",
                        o.value === sortMode ? "bg-blue-50 font-medium text-blue-700" : "text-gray-700 hover:bg-gray-50"
                      )}
                    >
                      {o.label}
                    </button>
                  ))}
                </div>
              </SheetContent>
            </Sheet>
            <Sheet open={filtersOpen} onOpenChange={setFiltersOpen}>
              <SheetTrigger asChild>
                <button type="button" className={PANEL_BUTTON}>
                  <SlidersHorizontal className="h-4 w-4" />
                  Filtrar
                  {activeFilters > 0 && <span className="text-blue-600">({activeFilters})</span>}
                </button>
              </SheetTrigger>
              <SheetContent side="left" className="flex w-[85%] flex-col p-0">
                <SheetTitle className="px-6 pt-6">Filtrar</SheetTitle>
                <div className="flex-1 overflow-y-auto px-6 pb-4">
                  <CatalogFilters {...filterProps} />
                </div>
                <div className="border-t p-4">
                  <button
                    type="button"
                    onClick={() => setFiltersOpen(false)}
                    className="w-full rounded-lg bg-blue-600 py-2.5 text-sm font-medium text-white hover:bg-blue-700"
                  >
                    Ver {plural(filtered.length, "resultado", "resultados")}
                  </button>
                </div>
              </SheetContent>
            </Sheet>
          </div>
        </div>

        <div className="mb-4 hidden justify-end md:flex">
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

        <GeaPartResults query={query} />

        {filtered.length > 0 ? (
          <div
            className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-3 xl:grid-cols-4"
            onClickCapture={() => session((s) => s.setItem(CATALOG_SCROLL_KEY, String(window.scrollY)))}
          >
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
