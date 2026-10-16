"use client";

import { useState } from "react";
import Image from "next/image";
import Link from "next/link";
import AddToCart from "@/components/catalog/AddToCart";
import { Product, ProductSummary } from "@/types/api";
import { cn, formatMoney, productHref } from "@/lib/utils";

// Takes a full catalog product or a related-product summary. versions: a mat family's
// versions in the catalog (the card then stands for all of them and links to the options).
export default function ProductCard({
  product,
  versions,
}: {
  product: ProductSummary & Pick<Partial<Product>, "discontinued" | "variant">;
  versions?: Product[];
}) {
  const family = versions && versions.length > 1 ? product.variant?.family : undefined;
  // The versions the product pages offer: one per set of options (the ERP can hold the same
  // options twice), in stock first, then the best seller - as api.services._variants picks.
  const shown = new Map<string, Product>();
  for (const v of [...(versions ?? [])].sort(
    (a, b) =>
      Number(!a.in_stock) - Number(!b.in_stock) ||
      (a.sold_rank ?? Infinity) - (b.sold_rank ?? Infinity) ||
      Number(a.key) - Number(b.key),
  )) {
    const options = JSON.stringify(v.variant?.options);
    if (!shown.has(options)) shown.set(options, v);
  }
  // A family card opens its best-selling version in stock; "Desde" is the lowest price those pages show.
  const lead = family ? [...shown.values()][0] : product;
  const prices = [...shown.values()].filter((v) => v.price_visible && v.price).map((v) => v.price as number);
  const images = product.images;
  const initialIndex = Math.max(
    images.findIndex((img) => img.is_primary),
    0
  );
  const [activeIndex, setActiveIndex] = useState(initialIndex);
  const [failed, setFailed] = useState(false);

  const activeImage = images[activeIndex];
  const imgSrc = failed || !activeImage ? "/placeholder.svg" : `/products/${activeImage.file}`;

  return (
    <div className="flex flex-col items-start rounded-xl border border-gray-200 bg-white p-3 sm:p-4 transition-shadow hover:shadow-md">
      {/* Square box, photo cropped to fill it, so every card lines up. */}
      <div className="relative aspect-square w-full overflow-hidden rounded-lg bg-gray-50">
        <Link
          href={productHref(lead.key, lead.slug)}
          aria-label={product.CNOMBREPRODUCTO}
          tabIndex={-1}
          className="absolute inset-0 z-[1]"
        />
        <Image
          src={imgSrc}
          alt={product.CNOMBREPRODUCTO}
          fill
          sizes="(min-width: 1280px) 20vw, (min-width: 1024px) 25vw, 50vw"
          className="object-cover"
          onError={() => setFailed(true)}
        />
        {images.length > 1 && (
          <div className="absolute bottom-1.5 left-1/2 z-[2] flex -translate-x-1/2 gap-1">
            {images.map((img, index) => (
              <button
                key={img.file}
                type="button"
                aria-label={`Ver imagen ${index + 1}`}
                onClick={() => {
                  setActiveIndex(index);
                  setFailed(false);
                }}
                className={`h-1.5 w-1.5 rounded-full ${
                  index === activeIndex ? "bg-gray-700" : "bg-gray-300"
                }`}
              />
            ))}
          </div>
        )}
      </div>
      <div className="mt-3 flex w-full flex-1 flex-col items-start">
        <h3 className="line-clamp-2 w-full text-sm font-medium leading-snug text-gray-800">
          <Link href={productHref(lead.key, lead.slug)} className="hover:text-blue-700">
            {family ? `Tapete ${family}` : product.CNOMBREPRODUCTO}
          </Link>
        </h3>
        {family ? (
          <>
            <p className="mt-1 text-xs text-gray-500">{shown.size} opciones</p>
            {prices.length > 0 && (
              <p className="mt-2 text-sm text-gray-500">
                Desde <span className="text-xl font-semibold text-gray-900 sm:text-2xl">{formatMoney(Math.min(...prices))}</span>
              </p>
            )}
            {/* Pinned to the bottom so the buttons line up across a row. */}
            <div className="mt-auto w-full pt-3">
              <Link
                href={productHref(lead.key, lead.slug)}
                className="flex items-center justify-center rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700"
              >
                Ver opciones
              </Link>
            </div>
          </>
        ) : (
          <>
            {product.CCODIGOPRODUCTO && <p className="mt-1 text-xs text-gray-400">SKU: {product.CCODIGOPRODUCTO}</p>}
            <Price product={product} className="mt-2" />
            <Availability product={product} className="mt-1" />
            {product.discontinued && (
              <p className="mt-1 text-xs font-medium text-amber-700">
                GEA ya no la surte
                {product.discontinued.replacement && ` · Reemplazo: ${product.discontinued.replacement}`}
              </p>
            )}
            {/* Pinned to the bottom so the buttons line up across a row. */}
            <AddToCart product={product} className="mt-auto pt-3" />
          </>
        )}
      </div>
    </div>
  );
}

export function Price({ product, className }: { product: ProductSummary; className?: string }) {
  if (!product.price_visible || product.price === null) {
    return <span className={cn("text-xs font-medium text-gray-400", className)}>Precio disponible para personal</span>;
  }
  if (product.price <= 0) {
    return <span className={cn("text-sm font-medium text-gray-400", className)}>Sin precio</span>;
  }
  return (
    <span className={cn("text-xl font-semibold text-gray-900 sm:text-2xl", className)}>
      {formatMoney(product.price)}
    </span>
  );
}

// Staff get the units in ALMACEN GENERAL; the public only whether there are any.
export function Availability({ product, className }: { product: ProductSummary; className?: string }) {
  const stock = product.stock ?? null;
  return (
    <p
      className={cn(
        "text-xs font-medium",
        product.in_stock ? "text-green-700" : product.on_order ? "text-amber-700" : "text-gray-400",
        className,
      )}
    >
      {!product.in_stock
        ? product.on_order
          ? "Sobre pedido"
          : "Sin existencia"
        : stock === null
          ? "Disponible"
          : `Disponible: ${stock.toLocaleString("es-MX", { maximumFractionDigits: 2 })} ${stock === 1 ? "unidad" : "unidades"}`}
    </p>
  );
}
