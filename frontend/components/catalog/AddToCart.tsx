"use client";

import { useState } from "react";
import Link from "next/link";
import { Check, ShoppingCart } from "lucide-react";
import { useCart } from "@/hooks/use-cart";
import { cn } from "@/lib/utils";
import { ProductImage } from "@/types/api";

interface Props {
  product: { CCODIGOPRODUCTO: string; CNOMBREPRODUCTO: string; images: ProductImage[] };
  withQuantity?: boolean; // the product page lets you pick how many
  className?: string;
}

// "Agregar" to the quote request; once added it says so and links to the cart.
export default function AddToCart({ product, withQuantity, className }: Props) {
  const { items, add } = useCart();
  const [quantity, setQuantity] = useState("1");
  const inCart = items.find((i) => i.code === product.CCODIGOPRODUCTO);
  const image = (product.images.find((i) => i.is_primary) ?? product.images[0])?.file ?? null;
  const qty = Number(quantity);
  const valid = Number.isFinite(qty) && qty > 0;

  return (
    <div className={cn("flex w-full flex-wrap items-center gap-2", className)}>
      {withQuantity && (
        <input
          type="number"
          min="1"
          step="1"
          inputMode="numeric"
          value={quantity}
          onChange={(e) => setQuantity(e.target.value)}
          aria-label="Cantidad"
          className="w-20 rounded-lg border border-gray-300 px-3 py-2 text-sm"
        />
      )}
      <button
        type="button"
        disabled={!valid}
        onClick={() =>
          add({ code: product.CCODIGOPRODUCTO, name: product.CNOMBREPRODUCTO, image }, withQuantity ? qty : 1)
        }
        className={cn(
          "inline-flex flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium disabled:opacity-50",
          inCart ? "border border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100" : "bg-blue-600 text-white hover:bg-blue-700",
        )}
      >
        {inCart ? <Check className="h-4 w-4" /> : <ShoppingCart className="h-4 w-4" />}
        {inCart ? `Agregar otro (${inCart.quantity})` : "Agregar"}
      </button>
      {inCart && withQuantity && (
        <Link href="/carrito" className="text-sm text-blue-600 hover:underline">
          Ver mi solicitud
        </Link>
      )}
    </div>
  );
}
