"use client";

import { useMemo, useState } from "react";
import { Plus } from "lucide-react";
import { normalize } from "@/components/catalog/CatalogFilters";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";
import { matchesQuery } from "@/lib/search";
import { formatMoney } from "@/lib/utils";
import { Product } from "@/types/api";

const MAX_RESULTS = 8;

// Staff adding a product to a request: searches the staff catalog, loaded the first time it's needed.
export default function AddProduct({ exclude, disabled, onAdd }: { exclude: string[]; disabled: boolean; onAdd: (code: string) => void }) {
  const [products, setProducts] = useState<Product[] | null>(null);
  const [query, setQuery] = useState("");
  const [failed, setFailed] = useState(false);

  const load = () => {
    if (products) return;
    apiFetch("/api/inventory/")
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setProducts)
      .catch(() => setFailed(true));
  };

  const results = useMemo(() => {
    const wanted = normalize(query.trim());
    if (!products || !wanted) return [];
    return products
      .filter((p) => p.CCODIGOPRODUCTO && !exclude.includes(p.CCODIGOPRODUCTO))
      .filter((p) => matchesQuery(normalize(`${p.CNOMBREPRODUCTO} ${p.CCODIGOPRODUCTO}`), wanted))
      .slice(0, MAX_RESULTS);
  }, [products, query, exclude]);

  return (
    <div className="mt-3">
      <Input
        type="search"
        value={query}
        onFocus={load}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Agregar producto: busca por nombre o SKU"
        aria-label="Agregar producto"
        className="sm:max-w-md"
      />
      {failed && <p className="mt-1 text-xs text-red-600">No se pudo cargar el catálogo.</p>}
      {query.trim() && products && results.length === 0 && <p className="mt-1 text-xs text-gray-500">Sin resultados.</p>}
      {results.length > 0 && (
        <ul className="mt-1 divide-y divide-gray-100 rounded-lg border border-gray-200 bg-white sm:max-w-md">
          {results.map((p) => (
            <li key={p.key}>
              <button
                type="button"
                disabled={disabled}
                onClick={() => {
                  onAdd(p.CCODIGOPRODUCTO!);
                  setQuery("");
                }}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-gray-50 disabled:opacity-50"
              >
                <Plus className="h-4 w-4 shrink-0 text-gray-400" />
                <span className="min-w-0 flex-1">
                  <span className="line-clamp-1 text-gray-800">{p.CNOMBREPRODUCTO}</span>
                  <span className="block text-xs text-gray-400">
                    SKU: {p.CCODIGOPRODUCTO} · Existencia: {Number(p.stock ?? 0)}
                    {p.price ? ` · ${formatMoney(p.price)}` : ""}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
