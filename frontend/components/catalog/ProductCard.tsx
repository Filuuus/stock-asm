"use client";

import { useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { Product, ProductSummary } from "@/types/api";
import { cn, formatMoney } from "@/lib/utils";

export default function ProductCard({ product }: { product: Product }) {
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
          href={productHref(product.CCODIGOPRODUCTO)}
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
      <div className="mt-3 flex w-full flex-col items-start">
        <h3 className="line-clamp-2 w-full text-sm font-medium leading-snug text-gray-800">
          <Link href={productHref(product.CCODIGOPRODUCTO)} className="hover:text-blue-700">
            {product.CNOMBREPRODUCTO}
          </Link>
        </h3>
        <p className="mt-1 text-xs text-gray-400">SKU: {product.CCODIGOPRODUCTO}</p>
        <Price product={product} className="mt-2" />
        <Availability product={product} className="mt-1" />
      </div>
    </div>
  );
}

export const productHref = (code: string) => `/producto/${encodeURIComponent(code)}`;

export function Price({ product, className }: { product: ProductSummary; className?: string }) {
  if (!product.price_visible || product.CPRECIO1 === null) {
    return <span className={cn("text-xs font-medium text-gray-400", className)}>Precio disponible para personal</span>;
  }
  if (product.CPRECIO1 <= 0) {
    return <span className={cn("text-sm font-medium text-gray-400", className)}>Sin precio</span>;
  }
  return (
    <span className={cn("text-xl font-semibold text-gray-900 sm:text-2xl", className)}>
      {formatMoney(product.CPRECIO1)}
    </span>
  );
}

// Staff get the units in ALMACEN GENERAL; the public only whether there are any.
export function Availability({ product, className }: { product: ProductSummary; className?: string }) {
  const stock = product.stock ?? null;
  return (
    <p className={cn("text-xs font-medium", product.in_stock ? "text-green-700" : "text-gray-400", className)}>
      {!product.in_stock
        ? "Sin existencia"
        : stock === null
          ? "Disponible"
          : `Disponible: ${stock.toLocaleString("es-MX", { maximumFractionDigits: 2 })} ${stock === 1 ? "unidad" : "unidades"}`}
    </p>
  );
}
