"use client";

import { useMemo, useState } from "react";
import { ChevronDown } from "lucide-react";
import CatalogHeader from "@/components/catalog/CatalogHeader";
import CatalogFilters from "@/components/catalog/CatalogFilters";
import ProductCard from "@/components/catalog/ProductCard";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Category, products } from "@/data/products";

type SortOption = "relevancia" | "precio-asc" | "precio-desc" | "nombre";

const sortLabels: Record<SortOption, string> = {
  relevancia: "Relevancia",
  "precio-asc": "Precio: menor a mayor",
  "precio-desc": "Precio: mayor a menor",
  nombre: "Nombre",
};

export default function Index() {
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<Category | "">("");
  const [activeBrands, setActiveBrands] = useState<string[]>([]);
  const [inStockOnly, setInStockOnly] = useState(false);
  const [minPrice, setMinPrice] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [sort, setSort] = useState<SortOption>("relevancia");
  const [filtersOpen, setFiltersOpen] = useState(false);

  const toggleBrand = (brand: string) => {
    setActiveBrands((prev) =>
      prev.includes(brand) ? prev.filter((b) => b !== brand) : [...prev, brand],
    );
  };

  const filteredProducts = useMemo(() => {
    const min = minPrice ? Number(minPrice) : undefined;
    const max = maxPrice ? Number(maxPrice) : undefined;
    const query = search.trim().toLowerCase();

    let result = products.filter((product) => {
      if (category && product.category !== category) return false;
      if (activeBrands.length > 0 && !activeBrands.includes(product.brand))
        return false;
      if (inStockOnly && product.stock <= 0) return false;
      if (min !== undefined && product.price < min) return false;
      if (max !== undefined && product.price > max) return false;
      if (
        query &&
        !product.name.toLowerCase().includes(query) &&
        !product.brand.toLowerCase().includes(query) &&
        !product.sku.toLowerCase().includes(query)
      )
        return false;
      return true;
    });

    result = [...result].sort((a, b) => {
      if (sort === "precio-asc") return a.price - b.price;
      if (sort === "precio-desc") return b.price - a.price;
      if (sort === "nombre") return a.name.localeCompare(b.name);
      return 0;
    });

    return result;
  }, [search, category, activeBrands, inStockOnly, minPrice, maxPrice, sort]);

  const filtersProps = {
    activeCategory: category,
    onCategoryChange: setCategory,
    activeBrands,
    onToggleBrand: toggleBrand,
    inStockOnly,
    onToggleInStock: setInStockOnly,
    minPrice,
    maxPrice,
    onMinPriceChange: setMinPrice,
    onMaxPriceChange: setMaxPrice,
  };

  return (
    <div className="flex min-h-screen flex-col items-center bg-gray-50">
      <CatalogHeader
        search={search}
        onSearchChange={setSearch}
        category={category}
        onCategoryChange={(value) => setCategory(value as Category | "")}
        cartCount={3}
        onOpenFilters={() => setFiltersOpen(true)}
      />

      <div className="flex w-full max-w-[1536px] flex-1 items-start">
        <aside className="sticky top-0 hidden h-screen w-[250px] shrink-0 overflow-auto border-r border-gray-200 bg-white lg:block">
          <CatalogFilters {...filtersProps} />
        </aside>

        <Sheet open={filtersOpen} onOpenChange={setFiltersOpen}>
          <SheetContent side="left" className="w-[280px] p-0 sm:w-[320px]">
            <SheetHeader className="border-b border-gray-200 px-4 py-3">
              <SheetTitle>Filtros</SheetTitle>
            </SheetHeader>
            <div className="overflow-auto">
              <CatalogFilters {...filtersProps} />
            </div>
          </SheetContent>
        </Sheet>

        <main className="flex flex-1 flex-col items-start gap-3 self-stretch p-4 sm:p-5">
          <div className="flex w-full flex-col gap-2 border-b border-gray-200 pb-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm leading-5 text-gray-600">
              <span className="font-medium text-gray-900">
                {filteredProducts.length}
              </span>{" "}
              resultado{filteredProducts.length === 1 ? "" : "s"}
            </p>
            <div className="flex items-center gap-2">
              <span className="text-xs leading-4 text-gray-500">
                Ordenar por:
              </span>
              <Select
                value={sort}
                onValueChange={(value) => setSort(value as SortOption)}
              >
                <SelectTrigger className="h-auto w-auto gap-1 rounded-[10px] border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 [&>svg]:hidden">
                  <SelectValue />
                  <ChevronDown size={12} className="text-gray-700" />
                </SelectTrigger>
                <SelectContent align="end">
                  {(Object.keys(sortLabels) as SortOption[]).map((option) => (
                    <SelectItem key={option} value={option}>
                      {sortLabels[option]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {filteredProducts.length > 0 ? (
            <div className="grid w-full grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {filteredProducts.map((product) => (
                <ProductCard key={product.id} product={product} />
              ))}
            </div>
          ) : (
            <div className="flex w-full flex-col items-center justify-center gap-1 rounded-xl border border-dashed border-gray-300 bg-white py-16 text-center">
              <p className="text-sm font-medium text-gray-700">
                No se encontraron productos
              </p>
              <p className="text-sm text-gray-400">
                Intenta ajustar los filtros o la búsqueda
              </p>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
