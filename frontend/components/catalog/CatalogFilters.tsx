import { Checkbox } from "@/components/ui/checkbox";
import { Switch } from "@/components/ui/switch";
import { brands, categories, Category } from "@/data/products";
import { cn } from "@/lib/utils";

interface CatalogFiltersProps {
  activeCategory: string;
  onCategoryChange: (value: Category | "") => void;
  activeBrands: string[];
  onToggleBrand: (brand: string) => void;
  inStockOnly: boolean;
  onToggleInStock: (value: boolean) => void;
  minPrice: string;
  maxPrice: string;
  onMinPriceChange: (value: string) => void;
  onMaxPriceChange: (value: string) => void;
}

export default function CatalogFilters({
  activeCategory,
  onCategoryChange,
  activeBrands,
  onToggleBrand,
  inStockOnly,
  onToggleInStock,
  minPrice,
  maxPrice,
  onMinPriceChange,
  onMaxPriceChange,
}: CatalogFiltersProps) {
  return (
    <div className="flex w-full flex-col items-start gap-6 p-4">
      <div className="flex w-full flex-col items-start gap-3">
        <h3 className="w-full text-xs font-semibold uppercase leading-4 tracking-[0.6px] text-gray-500">
          Categorías
        </h3>
        <ul className="flex w-full flex-col items-start gap-0.5">
          {categories.map((cat) => (
            <li key={cat} className="w-full">
              <button
                type="button"
                onClick={() =>
                  onCategoryChange(activeCategory === cat ? "" : cat)
                }
                className={cn(
                  "flex w-full items-center rounded-[10px] px-2 py-1 text-left text-sm leading-5 transition-colors",
                  activeCategory === cat
                    ? "bg-gray-100 font-medium text-gray-900"
                    : "text-gray-700 hover:bg-gray-50",
                )}
              >
                {cat}
              </button>
            </li>
          ))}
        </ul>
      </div>

      <div className="h-px w-full border-t border-gray-200" />

      <div className="flex w-full flex-col items-start gap-3">
        <h3 className="w-full text-xs font-semibold uppercase leading-4 tracking-[0.6px] text-gray-500">
          Marcas
        </h3>
        <ul className="flex w-full flex-col items-start gap-2">
          {brands.map(({ name, count }) => (
            <li key={name} className="flex w-full items-center gap-2.5">
              <Checkbox
                id={`brand-${name}`}
                checked={activeBrands.includes(name)}
                onCheckedChange={() => onToggleBrand(name)}
                className="h-4 w-4 rounded-[2.5px] border-gray-300 data-[state=checked]:border-select data-[state=checked]:bg-select"
              />
              <label
                htmlFor={`brand-${name}`}
                className="cursor-pointer text-sm leading-5 text-gray-700"
              >
                {name}
              </label>
              <span className="flex-1 text-right text-xs leading-4 text-gray-400">
                ({count})
              </span>
            </li>
          ))}
        </ul>
      </div>

      <div className="h-px w-full border-t border-gray-200" />

      <div className="flex w-full flex-col items-start gap-3">
        <h3 className="w-full text-xs font-semibold uppercase leading-4 tracking-[0.6px] text-gray-500">
          Disponibilidad
        </h3>
        <div className="flex items-center gap-2.5">
          <Switch
            checked={inStockOnly}
            onCheckedChange={onToggleInStock}
            className="data-[state=checked]:bg-brand"
          />
          <span className="text-sm leading-5 text-gray-700">
            Solo en stock
          </span>
        </div>
      </div>

      <div className="h-px w-full border-t border-gray-200" />

      <div className="flex w-full flex-col items-start gap-3">
        <h3 className="w-full text-xs font-semibold uppercase leading-4 tracking-[0.6px] text-gray-500">
          Rango de precio
        </h3>
        <div className="flex w-full items-center gap-2">
          <input
            type="number"
            inputMode="numeric"
            placeholder="$Min"
            value={minPrice}
            onChange={(e) => onMinPriceChange(e.target.value)}
            className="h-8 w-full min-w-0 flex-1 rounded-[10px] border border-gray-200 bg-white px-2 text-xs text-gray-900 placeholder:text-gray-400 outline-none focus:border-select"
          />
          <span className="text-xs leading-4 text-gray-400">—</span>
          <input
            type="number"
            inputMode="numeric"
            placeholder="$Max"
            value={maxPrice}
            onChange={(e) => onMaxPriceChange(e.target.value)}
            className="h-8 w-full min-w-0 flex-1 rounded-[10px] border border-gray-200 bg-white px-2 text-xs text-gray-900 placeholder:text-gray-400 outline-none focus:border-select"
          />
        </div>
      </div>
    </div>
  );
}
