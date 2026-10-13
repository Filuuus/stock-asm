import { cache } from "react";
import type { Metadata } from "next";
import { cookies } from "next/headers";
import { notFound, permanentRedirect } from "next/navigation";
import ProductDetailView from "@/components/catalog/ProductDetail";
import { productHref } from "@/lib/utils";
import { API_URL } from "@/lib/api";
import { ProductDetail } from "@/types/api";

type Props = {
  params: Promise<{ code: string }>; // "<key>-<slug>", or just the key
  searchParams: Promise<{ pieza?: string }>;
};

const keyOf = (code: string) => decodeURIComponent(code).split("-")[0];

// One fetch shared by the page and its title. Forwards the session cookie so
// prices, stock and staff notes follow the viewer's role (same as the catalog).
const getProduct = cache(async (key: string): Promise<ProductDetail | null> => {
  const cookieStore = await cookies();
  const res = await fetch(`${API_URL}/api/inventory/${encodeURIComponent(key)}/`, {
    headers: { Cookie: cookieStore.toString() },
    cache: "no-store",
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`No se pudo cargar el producto (${res.status})`);
  return res.json();
});

const primaryImage = (p: ProductDetail) => (p.images.find((i) => i.is_primary) ?? p.images[0])?.file;

// What search results and link previews show: the description's first line,
// else GEA's, else the name.
const summaryText = (p: ProductDetail) =>
  p.description?.split("\n")[0] || p.gea?.desc || p.CNOMBREPRODUCTO;

// Title, description and photo for the browser tab, shared links (WhatsApp,
// Facebook) and search results.
export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const product = await getProduct(keyOf((await params).code));
  if (!product) return {};
  const title = `${product.CNOMBREPRODUCTO} | Agropecuaria Santa María`;
  const image = primaryImage(product);
  return {
    title,
    description: summaryText(product),
    alternates: { canonical: productHref(product.key, product.slug) },
    openGraph: {
      title,
      description: summaryText(product),
      type: "website",
      locale: "es_MX",
      images: image ? [`/products/${image}`] : [],
    },
  };
}

// schema.org Product, so search engines can show price and availability.
function jsonLd(product: ProductDetail, siteUrl: string) {
  const image = primaryImage(product);
  const priced = product.price_visible && product.price !== null && product.price > 0;
  return {
    "@context": "https://schema.org",
    "@type": "Product",
    name: product.CNOMBREPRODUCTO,
    description: product.description ?? product.gea?.desc ?? undefined,
    image: image ? `${siteUrl}/products/${image}` : undefined,
    brand: product.brand ? { "@type": "Brand", name: product.brand } : undefined,
    offers: priced
      ? {
          "@type": "Offer",
          price: product.price,
          priceCurrency: "MXN",
          availability: product.in_stock
            ? "https://schema.org/InStock"
            : product.on_order
              ? "https://schema.org/BackOrder"
              : "https://schema.org/OutOfStock",
          url: `${siteUrl}${productHref(product.key, product.slug)}`,
        }
      : undefined,
  };
}

export default async function Page({ params, searchParams }: Props) {
  const { code } = await params;
  // ?pieza=<product key or, for staff, GEA code> opens the drawing with that part selected.
  const { pieza } = await searchParams;
  const product = await getProduct(keyOf(code));
  if (!product) notFound();

  // Old links (just the key) and renamed products land on the current URL.
  const canonical = productHref(product.key, product.slug);
  if (`/producto/${code}` !== canonical) {
    permanentRedirect(pieza ? `${canonical}?pieza=${encodeURIComponent(pieza)}` : canonical);
  }

  const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";
  return (
    <>
      <script
        type="application/ld+json"
        // "<" escaped so a product name can't close the script tag.
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd(product, siteUrl)).replace(/</g, "\\u003c") }}
      />
      {/* Keyed so moving between products or parts starts with a fresh selection. */}
      <ProductDetailView key={`${code}-${pieza ?? ""}`} product={product} highlight={pieza} />
    </>
  );
}
