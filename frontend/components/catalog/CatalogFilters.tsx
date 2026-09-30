import { cn } from "@/lib/utils";

export interface BrandOption {
  name: string;
  count: number;
}

interface CatalogFiltersProps {
  brands: BrandOption[];
  selectedBrands: Set<string>;
  onToggleBrand: (brand: string) => void;
  minPrice: string;
  maxPrice: string;
  onMinPriceChange: (value: string) => void;
  onMaxPriceChange: (value: string) => void;
  className?: string;
}

export default function CatalogFilters({
  brands,
  selectedBrands,
  onToggleBrand,
  minPrice,
  maxPrice,
  onMinPriceChange,
  onMaxPriceChange,
  className,
}: CatalogFiltersProps) {
  return (
    <aside className={cn("w-full md:w-64 flex-shrink-0 space-y-8 md:pr-4", className)}>
      <div>
        <h3 className="text-xs font-bold text-gray-400 tracking-wider mb-4">MARCAS</h3>
        <ul className="text-sm text-gray-600 space-y-3">
          {brands.map((brand) => (
            <li key={brand.name} className="flex items-center justify-between gap-2">
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={selectedBrands.has(brand.name)}
                  onChange={() => onToggleBrand(brand.name)}
                  className="rounded text-blue-600 border-gray-300 focus:ring-blue-500"
                />
                <span>{brand.name}</span>
              </label>
              <span className="text-xs text-gray-400 font-medium whitespace-nowrap">({brand.count})</span>
            </li>
          ))}
        </ul>
      </div>

      <div>
        <h3 className="text-xs font-bold text-gray-400 tracking-wider mb-4">RANGO DE PRECIO</h3>
        <div className="flex items-center space-x-2">
          <input
            type="number"
            min="0"
            value={minPrice}
            onChange={(e) => onMinPriceChange(e.target.value)}
            placeholder="$Min"
            className="w-full px-3 py-1.5 border border-gray-300 rounded text-sm text-gray-700 focus:outline-none focus:border-blue-500"
          />
          <span className="text-gray-400">-</span>
          <input
            type="number"
            min="0"
            value={maxPrice}
            onChange={(e) => onMaxPriceChange(e.target.value)}
            placeholder="$Max"
            className="w-full px-3 py-1.5 border border-gray-300 rounded text-sm text-gray-700 focus:outline-none focus:border-blue-500"
          />
        </div>
      </div>
    </aside>
  );
}
