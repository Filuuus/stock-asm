"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ExternalLink, Loader2 } from "lucide-react";
import ProductDetailView from "@/components/catalog/ProductDetail";
import { Notice } from "@/components/notice";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { apiFetch } from "@/lib/api";
import { productHref } from "@/lib/utils";
import type { ProductDetail } from "@/types/api";

// A product's page in a dialog, so a list can show a part without leaving it; the full page opens only
// from "Abrir página completa". productKey = the catalog key (the ERP product id). Links to other
// products inside it (related parts, "aparece en") switch the dialog to that product.
export default function ProductDialog({
  productKey,
  fallbackName,
  onClose,
}: {
  productKey: string;
  fallbackName: string;
  onClose: () => void;
}) {
  const [key, setKey] = useState(productKey);
  const [product, setProduct] = useState<ProductDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiFetch(`/api/inventory/${encodeURIComponent(key)}/`)
      .then((r) => {
        if (r.status === 404) throw new Error("Esta pieza no está en el catálogo.");
        if (!r.ok) throw new Error("No se pudo cargar la pieza.");
        return r.json();
      })
      .then((p) => !cancelled && setProduct(p))
      .catch((e) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [key]);

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-6xl w-[calc(100%-2rem)] max-h-[90vh] overflow-y-auto grid-cols-[minmax(0,1fr)]">
        <DialogHeader className="pr-8 text-left">
          <div className="flex min-h-5 flex-wrap items-center justify-end gap-2">
            {/* The product page shows the name as its heading; the title stays for screen readers. */}
            <DialogTitle className="sr-only">{product?.CNOMBREPRODUCTO ?? fallbackName}</DialogTitle>
            {product && (
              <Link
                href={productHref(product.key, product.slug)}
                className="inline-flex items-center gap-1 text-sm text-blue-600 hover:underline"
              >
                Abrir página completa
                <ExternalLink className="h-3.5 w-3.5" />
              </Link>
            )}
          </div>
        </DialogHeader>
        {error ? (
          <Notice tone="info" title={error} />
        ) : product ? (
          <div
            onClickCapture={(e) => {
              const link = (e.target as HTMLElement).closest("a");
              const match = link?.getAttribute("href")?.match(/^\/producto\/([^-/?#]+)/);
              if (!match) return;
              e.preventDefault();
              e.stopPropagation();
              setProduct(null);
              setError(null);
              setKey(decodeURIComponent(match[1]));
            }}
          >
            <ProductDetailView product={product} embedded />
          </div>
        ) : (
          <p className="flex items-center gap-2 text-sm text-gray-500">
            <Loader2 className="h-4 w-4 animate-spin" />
            Cargando…
          </p>
        )}
      </DialogContent>
    </Dialog>
  );
}
