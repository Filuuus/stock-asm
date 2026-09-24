"use client";

import { useState } from "react";
import Image from "next/image";
import { Product } from "@/types/api";

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
    <div className="flex flex-col items-start rounded-xl border border-gray-200 bg-white p-4 transition-shadow hover:shadow-md">
      <div className="relative flex h-40 w-full items-center justify-center overflow-hidden rounded-lg bg-gray-50">
        <Image
          src={imgSrc}
          alt={product.CNOMBREPRODUCTO}
          fill
          className="object-contain"
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
        {product.CTEXTOEXTRA1 && (
          <span className="inline-flex items-center rounded bg-blue-50 px-2 py-0.5 text-xs font-semibold text-blue-700">
            {product.CTEXTOEXTRA1}
          </span>
        )}
        <h3 className="mt-1.5 line-clamp-2 w-full text-sm font-medium leading-snug text-gray-800">
          {product.CNOMBREPRODUCTO}
        </h3>
        <p className="mt-1 text-xs text-gray-400">SKU: {product.CCODIGOPRODUCTO}</p>
        {product.price_visible && product.CPRECIO1 !== null ? (
          <span className="mt-2 text-lg font-bold text-gray-900">
            ${product.CPRECIO1.toLocaleString("es-MX", { minimumFractionDigits: 2 })}
          </span>
        ) : (
          <span className="mt-2 text-xs font-medium text-gray-400">
            Precio disponible para personal
          </span>
        )}
      </div>
    </div>
  );
}
