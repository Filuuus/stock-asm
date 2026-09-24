"use client";

import { useMemo, useState } from "react";
import ProductCard from "@/components/catalog/ProductCard";
import CatalogFilters, { BrandOption } from "@/components/catalog/CatalogFilters";
import { useSearchQuery } from "@/hooks/use-search-query";
import { Product } from "@/types/api";

type SortMode = "relevance" | "price-asc" | "price-desc";

function normalize(text: string) {
  return text
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();
}

export default function CatalogView({ products }: { products: Product[] }) {
  const { query } = useSearchQuery();
  const [selectedBrands, setSelectedBrands] = useState<Set<string>>(new Set());
  const [minPrice, setMinPrice] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [sortMode, setSortMode] = useState<SortMode>("relevance");

  const brands: BrandOption[] = useMemo(() => {
    const counts = new Map<string, number>();
    for (const product of products) {
      if (product.brand) {
        counts.set(product.brand, (counts.get(product.brand) ?? 0) + 1);
      }
    }
    return [...counts.entries()]
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count);
  }, [products]);

  const toggleBrand = (brand: string) => {
    setSelectedBrands((prev) => {
      const next = new Set(prev);
      if (next.has(brand)) {
        next.delete(brand);
      } else {
        next.add(brand);
      }
      return next;
    });
  };

  const filtered = useMemo(() => {
    const normalizedQuery = normalize(query.trim());
    const min = minPrice ? parseFloat(minPrice) : null;
    const max = maxPrice ? parseFloat(maxPrice) : null;

    let result = products.filter((product) => {
      if (selectedBrands.size > 0 && (!product.brand || !selectedBrands.has(product.brand))) {
        return false;
      }
      if (min !== null || max !== null) {
        // A hidden price can't be verified to fall in range - exclude it
        // rather than guessing, only when a range filter is actually set.
        if (product.CPRECIO1 === null) return false;
        if (min !== null && product.CPRECIO1 < min) return false;
        if (max !== null && product.CPRECIO1 > max) return false;
      }
      if (normalizedQuery) {
        const haystack = normalize(`${product.CNOMBREPRODUCTO} ${product.CCODIGOPRODUCTO}`);
        if (!haystack.includes(normalizedQuery)) return false;
      }
      return true;
    });

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
  }, [products, selectedBrands, minPrice, maxPrice, sortMode, query]);

  return (
    <main className="flex flex-col md:flex-row max-w-7xl mx-auto w-full gap-8 p-6">
      <CatalogFilters
        brands={brands}
        selectedBrands={selectedBrands}
        onToggleBrand={toggleBrand}
        minPrice={minPrice}
        maxPrice={maxPrice}
        onMinPriceChange={setMinPrice}
        onMaxPriceChange={setMaxPrice}
      />

      <div className="flex-1 flex flex-col">
        <div className="flex items-center justify-between mb-6 pb-4 border-b border-gray-200">
          <span className="text-sm text-gray-500 font-medium">
            Mostrando {filtered.length} productos
          </span>
          <div className="flex items-center space-x-2 text-sm text-gray-600">
            <span>Ordenar por:</span>
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
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
            {filtered.map((product) => (
              <ProductCard key={product.CIDPRODUCTO} product={product} />
            ))}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-gray-300 bg-white py-16 text-center">
            <p className="text-sm font-medium text-gray-700">No hay productos disponibles</p>
          </div>
        )}
      </div>
    </main>
  );
}
