"use client";

import { useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Notice } from "@/components/notice";
import { productHref } from "@/components/catalog/ProductCard";
import { useCart } from "@/hooks/use-cart";
import { apiFetch } from "@/lib/api";
import { plural } from "@/lib/utils";

// The quote-request cart: prices stay private, so the customer sends the list
// and management approves it; their personal link then shows the prices.
export default function CartPage() {
  const router = useRouter();
  const { items, setQuantity, remove, clear } = useCart();
  const [form, setForm] = useState({ name: "", phone: "", company: "", note: "" });
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const field = (key: keyof typeof form) => ({
    value: form[key],
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      setForm((f) => ({ ...f, [key]: e.target.value })),
  });

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (items.some((i) => !(i.quantity > 0))) {
      setError("Revisa las cantidades: todas deben ser mayores a cero.");
      return;
    }
    setSending(true);
    try {
      const res = await apiFetch("/api/solicitudes/", {
        method: "POST",
        body: JSON.stringify({ ...form, items: items.map((i) => ({ code: i.code, quantity: i.quantity })) }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(data.error ?? "No se pudo enviar la solicitud. Intenta de nuevo.");
        return;
      }
      clear();
      router.push(`/solicitud/${data.token}`);
    } catch {
      setError("No se pudo enviar la solicitud. Revisa tu conexión e intenta de nuevo.");
    } finally {
      setSending(false);
    }
  };

  if (items.length === 0) {
    return (
      <main className="mx-auto w-full max-w-3xl p-4 sm:p-6">
        <h1 className="text-2xl font-semibold text-gray-900">Mi solicitud</h1>
        <div className="mt-6 rounded-lg border border-dashed border-gray-300 bg-white py-10 text-center">
          <p className="text-sm text-gray-500">Tu solicitud está vacía.</p>
          <Link href="/" className="mt-2 inline-block text-sm text-blue-600 hover:underline">
            Ir al catálogo
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto w-full max-w-3xl p-4 sm:p-6">
      <h1 className="text-2xl font-semibold text-gray-900">Mi solicitud</h1>
      <p className="mt-1 text-sm text-gray-500">
        {plural(items.length, "producto", "productos")}. Envíala y te compartimos los precios en cuanto la revisemos.
      </p>

      <ul className="mt-6 divide-y divide-gray-100 rounded-lg border border-gray-200 bg-white">
        {items.map((item) => (
          <li key={item.code} className="flex items-center gap-3 p-3 sm:p-4">
            <div className="relative h-14 w-14 shrink-0 overflow-hidden rounded bg-gray-50">
              <Image
                src={item.image ? `/products/${item.image}` : "/placeholder.svg"}
                alt=""
                fill
                sizes="56px"
                className="object-cover"
              />
            </div>
            <div className="min-w-0 flex-1">
              <Link href={productHref(item.code)} className="line-clamp-2 text-sm font-medium text-gray-800 hover:text-blue-700">
                {item.name}
              </Link>
              <p className="text-xs text-gray-400">SKU: {item.code}</p>
            </div>
            <input
              type="number"
              min="1"
              step="1"
              inputMode="numeric"
              value={item.quantity || ""}
              onChange={(e) => setQuantity(item.code, Math.max(0, Number(e.target.value)))}
              aria-label={`Cantidad de ${item.name}`}
              className="w-20 shrink-0 rounded-lg border border-gray-300 px-2 py-1.5 text-sm"
            />
            <button
              type="button"
              onClick={() => remove(item.code)}
              aria-label={`Quitar ${item.name}`}
              className="shrink-0 rounded p-2 text-gray-400 hover:bg-gray-100 hover:text-red-600"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          </li>
        ))}
      </ul>

      <form onSubmit={submit} className="mt-8 space-y-4 rounded-lg border border-gray-200 bg-white p-4 sm:p-6">
        <h2 className="text-lg font-semibold text-gray-900">Tus datos</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="name">Nombre *</Label>
            <Input id="name" required maxLength={120} autoComplete="name" {...field("name")} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="phone">Teléfono (WhatsApp) *</Label>
            <Input id="phone" required type="tel" maxLength={30} autoComplete="tel" placeholder="10 dígitos" {...field("phone")} />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="company">Rancho o empresa</Label>
            <Input id="company" maxLength={120} autoComplete="organization" {...field("company")} />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="note">Nota</Label>
            <Textarea id="note" maxLength={2000} rows={3} placeholder="Algo que debamos saber" {...field("note")} />
          </div>
        </div>
        {error && <Notice tone="error" title={error} />}
        <Button type="submit" disabled={sending} className="w-full sm:w-auto">
          {sending ? "Enviando…" : "Enviar solicitud"}
        </Button>
      </form>
    </main>
  );
}
