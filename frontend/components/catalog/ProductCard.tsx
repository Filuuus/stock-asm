"use client";

import { useState } from "react";
import Image from "next/image";
import { Product } from "@/types/api";

export default function ProductCard({ product }: { product: Product }) {
  const [imgSrc, setImgSrc] = useState(`/products/${product.CCODIGOPRODUCTO}.webp`);

  return (
    <div className="flex flex-col items-start rounded-xl border border-gray-200 bg-white p-4 transition-shadow hover:shadow-md">
      <div className="relative flex h-40 w-full items-center justify-center overflow-hidden rounded-lg bg-gray-50">
        <Image
          src={imgSrc}
          alt={product.CNOMBREPRODUCTO}
          fill
          className="object-contain"
          onError={() => setImgSrc("/placeholder.svg")}
        />
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
        <span className="mt-2 text-lg font-bold text-gray-900">
          ${product.CPRECIO1.toLocaleString("es-MX", { minimumFractionDigits: 2 })}
        </span>
      </div>
    </div>
  );
}
