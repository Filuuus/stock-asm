import { cookies } from "next/headers";
import CatalogView from "@/components/catalog/CatalogView";
import { API_URL } from "@/lib/api";
import { Product } from "@/types/api";

async function getInventory(): Promise<Product[]> {
  try {
    // Forward the browser's session cookie so the backend knows who's
    // asking and can decide which prices are visible (see api/services.py
    // get_inventory_catalog) - without this, server-side rendering would
    // always see an anonymous request even for a logged-in worker.
    const cookieStore = await cookies();
    const res = await fetch(`${API_URL}/api/inventory/`, {
      headers: { Cookie: cookieStore.toString() },
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
