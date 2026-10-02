import { cache } from "react";
import type { Metadata } from "next";
import { cookies } from "next/headers";
import { notFound } from "next/navigation";
import ProductDetailView from "@/components/catalog/ProductDetail";
import { API_URL } from "@/lib/api";
import { ProductDetail } from "@/types/api";

type Props = {
  params: Promise<{ code: string }>;
  searchParams: Promise<{ pieza?: string }>;
};

// One fetch shared by the page and its title. Forwards the session cookie so
// prices, stock and staff notes follow the viewer's role (same as the catalog).
const getProduct = cache(async (code: string): Promise<ProductDetail | null> => {
  const cookieStore = await cookies();
  const res = await fetch(`${API_URL}/api/inventory/${encodeURIComponent(decodeURIComponent(code))}/`, {
    headers: { Cookie: cookieStore.toString() },
    cache: "no-store",
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`No se pudo cargar el producto (${res.status})`);
  return res.json();
});

// The product's name in the browser tab, shared links and search results.
export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const product = await getProduct((await params).code);
  if (!product) return {};
  return {
    title: `${product.CNOMBREPRODUCTO} | Agropecuaria Santa María`,
    description: product.gea?.desc ?? `SKU ${product.CCODIGOPRODUCTO}`,
  };
}

export default async function Page({ params, searchParams }: Props) {
  const { code } = await params;
  // ?pieza=<code> opens the drawing with that part selected (from "Aparece en").
  const { pieza } = await searchParams;
  const product = await getProduct(code);
  if (!product) notFound();

  // Keyed so moving between products or parts starts with a fresh selection.
  return <ProductDetailView key={`${code}-${pieza ?? ""}`} product={product} highlight={pieza} />;
}
