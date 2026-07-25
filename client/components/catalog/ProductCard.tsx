import { brandBadgeStyles, formatPrice, LOW_STOCK_THRESHOLD, Product } from "@/data/products";
import { cn } from "@/lib/utils";

function ProductImagePlaceholder() {
  return (
    <svg
      width="48"
      height="48"
      viewBox="0 0 48 48"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path
        d="M22 43.46C22.6081 43.8111 23.2979 43.9959 24 43.9959C24.7021 43.9959 25.3919 43.8111 26 43.46L40 35.46C40.6075 35.1093 41.112 34.605 41.4631 33.9977C41.8141 33.3904 41.9993 32.7014 42 32V16C41.9993 15.2985 41.8141 14.6096 41.4631 14.0023C41.112 13.395 40.6075 12.8907 40 12.54L26 4.53999C25.3919 4.18891 24.7021 4.00409 24 4.00409C23.2979 4.00409 22.6081 4.18891 22 4.53999L8 12.54C7.39253 12.8907 6.88796 13.395 6.53692 14.0023C6.18589 14.6096 6.00072 15.2985 6 16V32C6.00072 32.7014 6.18589 33.3904 6.53692 33.9977C6.88796 34.605 7.39253 35.1093 8 35.46L22 43.46Z"
        stroke="#D1D5DB"
        strokeWidth="4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M24 44V24"
        stroke="#D1D5DB"
        strokeWidth="4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M6.6 14L22.006 23.468C22.6126 23.8168 23.3002 24.0004 24 24.0004C24.6998 24.0004 25.3873 23.8168 25.994 23.468L41.4 14"
        stroke="#D1D5DB"
        strokeWidth="4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M15 8.54L33 18.84"
        stroke="#D1D5DB"
        strokeWidth="4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export default function ProductCard({ product }: { product: Product }) {
  const lowStock = product.stock <= LOW_STOCK_THRESHOLD;

  return (
    <div className="flex flex-col items-start rounded-xl border border-gray-200 bg-white transition-shadow hover:shadow-md">
      <div className="flex h-40 w-full items-center justify-center border-b border-gray-100 bg-gray-50">
        <ProductImagePlaceholder />
      </div>
      <div className="flex w-full flex-col items-start p-3">
        <span
          className={cn(
            "inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold leading-[15px]",
            brandBadgeStyles[product.brand],
          )}
        >
          {product.brand}
        </span>
        <h3 className="mt-1.5 line-clamp-2 w-full text-sm font-medium leading-[17.5px] text-gray-800">
          {product.name}
        </h3>
        <p className="mt-1 w-full text-xs leading-4 text-gray-400">
          {product.sku}
        </p>
        <span className="mt-2 w-full text-xl font-bold leading-7 text-gray-900">
          {formatPrice(product.price)}
        </span>
        <span
          className={cn(
            "mt-1.5 inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium leading-[15px]",
            lowStock
              ? "bg-red-50 text-red-700"
              : "bg-green-50 text-green-700",
          )}
        >
          {lowStock ? `Bajo stock: ${product.stock}` : `En stock: ${product.stock}`}
        </span>
      </div>
    </div>
  );
}
