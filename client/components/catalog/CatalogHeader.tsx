import { Search, Settings, ShoppingCart, User, Menu } from "lucide-react";
import { categories } from "@/data/products";

interface CatalogHeaderProps {
  search: string;
  onSearchChange: (value: string) => void;
  category: string;
  onCategoryChange: (value: string) => void;
  cartCount: number;
  onOpenFilters: () => void;
}

export default function CatalogHeader({
  search,
  onSearchChange,
  category,
  onCategoryChange,
  cartCount,
  onOpenFilters,
}: CatalogHeaderProps) {
  return (
    <header className="flex flex-col items-start bg-gray-900">
      <div className="mx-auto flex w-full max-w-[1920px] flex-col gap-3 px-4 py-3 sm:px-6 lg:h-14 lg:flex-row lg:items-center lg:gap-4 lg:py-0 xl:px-[216px]">
        <div className="flex items-center justify-between gap-3">
          <span className="whitespace-nowrap text-base font-bold leading-6 tracking-[-0.4px] text-white">
            Agropecuaria Santa María
          </span>
          <button
            type="button"
            onClick={onOpenFilters}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-white lg:hidden"
            aria-label="Abrir filtros"
          >
            <Menu size={20} />
          </button>
        </div>

        <div className="flex min-w-0 flex-1 items-stretch lg:px-4">
          <select
            value={category}
            onChange={(e) => onCategoryChange(e.target.value)}
            className="hidden shrink-0 rounded-l-xl border-r border-gray-300 bg-gray-200 px-4 py-0 text-xs font-medium text-gray-700 outline-none sm:block"
            aria-label="Filtrar por categoría"
          >
            <option value="">Todas las categorías</option>
            {categories.map((cat) => (
              <option key={cat} value={cat}>
                {cat}
              </option>
            ))}
          </select>
          <div className="relative flex flex-1 items-stretch">
            <input
              type="text"
              value={search}
              onChange={(e) => onSearchChange(e.target.value)}
              placeholder="Buscar productos, marcas, ID..."
              className="h-10 w-full rounded-l-xl bg-white px-4 text-sm text-gray-900 placeholder:text-gray-400 outline-none sm:rounded-l-none"
            />
            <button
              type="button"
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-r-xl bg-brand text-white transition-colors hover:bg-green-700"
              aria-label="Buscar"
            >
              <Search size={16} />
            </button>
          </div>
        </div>

        <div className="flex items-center gap-1 self-end lg:self-auto">
          <button
            type="button"
            className="flex items-center gap-1.5 rounded-xl px-3 py-2 text-white hover:bg-white/10"
          >
            <User size={20} />
            <span className="hidden text-xs font-medium leading-4 sm:inline">
              Mi cuenta
            </span>
          </button>
          <button
            type="button"
            aria-label="Configuración"
            className="flex items-center rounded-xl px-3 py-2 text-white hover:bg-white/10"
          >
            <Settings size={20} />
          </button>
          <button
            type="button"
            aria-label="Carrito"
            className="relative flex items-center rounded-xl px-3 py-2 text-white hover:bg-white/10"
          >
            <ShoppingCart size={20} />
            {cartCount > 0 && (
              <span className="absolute -right-0.5 -top-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-brand text-[10px] font-bold leading-[15px] text-white">
                {cartCount}
              </span>
            )}
          </button>
        </div>
      </div>
    </header>
  );
}
