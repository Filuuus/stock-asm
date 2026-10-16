import type { Metadata } from "next";
import { cookies } from "next/headers";
import CatalogView from "@/components/catalog/CatalogView";
import { API_URL } from "@/lib/api";
import { Product } from "@/types/api";

export const metadata: Metadata = { title: "Catálogo | Agropecuaria Santa María" };

async function getInventory(): Promise<Product[]> {
  // Forward the browser's session cookie so the backend knows who's
  // asking and can decide which prices are visible (see api/services.py
  // get_inventory_catalog) - without this, server-side rendering would
  // always see an anonymous request even for a logged-in worker.
  // Outside the try: cookies() throws Next's signal that the page renders per
  // request, and catching it made the build prerender the catalog once, statically.
  const cookieStore = await cookies();
  try {
    const res = await fetch(`${API_URL}/api/inventory/`, {
      headers: { Cookie: cookieStore.toString() },
      cache: "no-store",
    });
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

export default async function Page() {
  const products = await getInventory();

  return <CatalogView products={products} />;
}
