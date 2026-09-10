import ProductCard from "@/components/catalog/ProductCard";
import CatalogFilters from "@/components/catalog/CatalogFilters";
import { Product } from "@/types/api";

async function getInventory(): Promise<Product[]> {
  try {
    const res = await fetch("http://127.0.0.1:8000/api/inventory/", {
      cache: "no-store",
    });
    if (!res.ok) return [];
    return res.json();
  } catch (error) {
    return [];
  }
}

export default async function Page() {
  const products = await getInventory();

  return (
    <main className="flex flex-col md:flex-row max-w-7xl mx-auto w-full gap-8 p-6">
      <CatalogFilters />

      <div className="flex-1 flex flex-col">
        <div className="flex items-center justify-between mb-6 pb-4 border-b border-gray-200">
          <span className="text-sm text-gray-500 font-medium">
            Mostrando {products.length} productos
          </span>
          <div className="flex items-center space-x-2 text-sm text-gray-600">
            <span>Ordenar por:</span>
            <select className="border border-gray-300 rounded px-2 py-1 bg-white focus:outline-none">
              <option>Relevancia</option>
              <option>Precio: Menor a Mayor</option>
              <option>Precio: Mayor a Menor</option>
            </select>
          </div>
        </div>

        {products.length > 0 ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
            {products.map((product) => (
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
