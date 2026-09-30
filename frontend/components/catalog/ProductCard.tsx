"use client";

import { useState } from "react";
import Image from "next/image";
import { Product } from "@/types/api";
import { formatMoney } from "@/lib/utils";

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
        <Image
          src={imgSrc}
          alt={product.CNOMBREPRODUCTO}
          fill
          sizes="(min-width: 1280px) 20vw, (min-width: 1024px) 25vw, 50vw"
          className="object-cover"
          onError={() => setFailed(true)}
        />
        {images.length > 1 && (
          <div className="absolute bottom-1.5 left-1/2 flex -translate-x-1/2 gap-1">
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
          {product.CNOMBREPRODUCTO}
        </h3>
        <p className="mt-1 text-xs text-gray-400">SKU: {product.CCODIGOPRODUCTO}</p>
        {product.price_visible && product.CPRECIO1 !== null ? (
          product.CPRECIO1 > 0 ? (
            <span className="mt-2 text-xl font-semibold text-gray-900 sm:text-2xl">
              {formatMoney(product.CPRECIO1)}
            </span>
          ) : (
            <span className="mt-2 text-sm font-medium text-gray-400">Sin precio</span>
          )
        ) : (
          <span className="mt-2 text-xs font-medium text-gray-400">
            Precio disponible para personal
          </span>
        )}
        {/* Staff get the units in ALMACEN GENERAL; the public only whether there are any. */}
        <p className={`mt-1 text-xs font-medium ${product.in_stock ? "text-green-700" : "text-gray-400"}`}>
          {!product.in_stock
            ? "Sin existencia"
            : product.stock === null
              ? "Disponible"
              : `Disponible: ${product.stock.toLocaleString("es-MX", { maximumFractionDigits: 2 })} ${product.stock === 1 ? "unidad" : "unidades"}`}
        </p>
      </div>
    </div>
  );
}
