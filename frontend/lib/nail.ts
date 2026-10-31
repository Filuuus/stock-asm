import { API_URL } from "@/lib/api";
import { Product } from "@/types/api";

// The nails sold with mats, for the mat calculators (public catalog, cached hourly).
export async function getNail(): Promise<Product | null> {
  try {
    const res = await fetch(`${API_URL}/api/inventory/`, { next: { revalidate: 3600 } });
    const products: Product[] = res.ok ? await res.json() : [];
    return products.find((p) => p.category === "R_NW" && /CLAVO ESPECIAL/i.test(p.CNOMBREPRODUCTO) && p.in_stock && p.price) ?? null;
  } catch {
    return null;
  }
}
