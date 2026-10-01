import { cookies } from "next/headers";
import { notFound } from "next/navigation";
import ProductDetailView from "@/components/catalog/ProductDetail";
import { API_URL } from "@/lib/api";
import { ProductDetail } from "@/types/api";

export default async function Page({
  params,
  searchParams,
}: {
  params: Promise<{ code: string }>;
  searchParams: Promise<{ pieza?: string }>;
}) {
  const { code } = await params;
  // ?pieza=<code> opens the drawing with that part selected (from "Aparece en").
  const { pieza } = await searchParams;
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

  // Keyed so moving between products or parts starts with a fresh selection.
  return <ProductDetailView key={`${code}-${pieza ?? ""}`} product={product} highlight={pieza} />;
}
