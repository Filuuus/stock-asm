"use client";

import { createContext, useContext, useMemo, useSyncExternalStore, type ReactNode } from "react";

// The quote-request cart. Kept in this browser only (localStorage) until it's
// sent; prices are never stored here - they stay private until management
// approves the request.
export interface CartItem {
  key: string; // the product's public key
  name: string;
  image: string | null; // file under /products/
  quantity: number;
}

// v2: items by product key instead of code (v1 carts are dropped).
const STORAGE_KEY = "cart-v2";
const EMPTY: CartItem[] = [];
const listeners = new Set<() => void>();
let cached: { raw: string | null; items: CartItem[] } = { raw: null, items: EMPTY };

function snapshot(): CartItem[] {
  let raw: string | null = null;
  try {
    raw = localStorage.getItem(STORAGE_KEY);
  } catch {
    // private mode / blocked storage: behaves as an empty cart
  }
  if (raw !== cached.raw) {
    try {
      cached = { raw, items: raw ? JSON.parse(raw) : EMPTY };
    } catch {
      cached = { raw, items: EMPTY };
    }
  }
  return cached.items;
}

function write(items: CartItem[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
  } catch {
    cached = { raw: null, items }; // storage unavailable: keep it for this visit
  }
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  // Another tab changed the cart.
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

interface CartContextValue {
  items: CartItem[];
  count: number;
  add: (item: Omit<CartItem, "quantity">, quantity?: number) => void;
  setQuantity: (key: string, quantity: number) => void;
  remove: (key: string) => void;
  clear: () => void;
}

const CartContext = createContext<CartContextValue | null>(null);

export function CartProvider({ children }: { children: ReactNode }) {
  // The server (and the first client render) sees an empty cart, so the
  // markup matches; the saved cart appears right after.
  const items = useSyncExternalStore(subscribe, snapshot, () => EMPTY);

  const value = useMemo<CartContextValue>(
    () => ({
      items,
      count: items.length,
      add: (item, quantity = 1) => {
        const current = snapshot();
        write(
          current.some((i) => i.key === item.key)
            ? current.map((i) => (i.key === item.key ? { ...i, quantity: i.quantity + quantity } : i))
            : [...current, { ...item, quantity }],
        );
      },
      setQuantity: (key, quantity) => write(snapshot().map((i) => (i.key === key ? { ...i, quantity } : i))),
      remove: (key) => write(snapshot().filter((i) => i.key !== key)),
      clear: () => write(EMPTY),
    }),
    [items],
  );

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

export function useCart() {
  const ctx = useContext(CartContext);
  if (!ctx) throw new Error("useCart must be used inside CartProvider");
  return ctx;
}
