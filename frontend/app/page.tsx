import CatalogView from "@/components/catalog/CatalogView";
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

  return <CatalogView products={products} />;
}
