import { cookies } from "next/headers";
import { notFound } from "next/navigation";
import ProductDetailView from "@/components/catalog/ProductDetail";
import { API_URL } from "@/lib/api";
import { ProductDetail } from "@/types/api";

export default async function Page({ params }: { params: Promise<{ code: string }> }) {
  const { code } = await params;
  // Forward the session cookie so prices, stock and staff notes follow the
  // viewer's role (same as the catalog page).
  const cookieStore = await cookies();
  const res = await fetch(`${API_URL}/api/inventory/${encodeURIComponent(decodeURIComponent(code))}/`, {
    headers: { Cookie: cookieStore.toString() },
    cache: "no-store",
  });
  if (res.status === 404) notFound();
  if (!res.ok) throw new Error(`No se pudo cargar el producto (${res.status})`);
  const product: ProductDetail = await res.json();

  return <ProductDetailView product={product} />;
}
