import type { Metadata } from "next";
import MatCalculator from "@/components/landing/MatCalculator";
import { API_URL } from "@/lib/api";
import { Product } from "@/types/api";

export const metadata: Metadata = {
  title: "Calculadora de tapetes | Agropecuaria Santa María",
  description: "Calcule cuántos tapetes de hule y clavos necesita su establo, con precios del catálogo.",
};

const byRank = (a: Product, b: Product) => (a.sold_rank ?? Infinity) - (b.sold_rank ?? Infinity);
const offered = (p: Product) => p.category === "R_NW" && !!p.price && (p.in_stock || p.on_order);

// Public prices (no cookie), rebuilt at most hourly like the home page.
async function getProducts(): Promise<Product[]> {
  try {
    const res = await fetch(`${API_URL}/api/inventory/`, { next: { revalidate: 3600 } });
    return res.ok ? res.json() : [];
  } catch {
    return [];
  }
}

export default async function Page() {
  const products = (await getProducts()).filter(offered).sort(byRank);
  // Only full 4 × 6 ft cow mats: the calculator counts in that size.
  const mats = products.filter((p) => /4 X 6|MAXGRIP/i.test(p.CNOMBREPRODUCTO));
  const nail = products.find((p) => /CLAVO ESPECIAL/i.test(p.CNOMBREPRODUCTO) && p.in_stock) ?? null;

  return (
    <main className="mx-auto w-full max-w-5xl px-4 py-10 sm:px-6">
      <h1 className="text-2xl font-bold text-slate-900 sm:text-3xl">Calculadora de tapetes</h1>
      <p className="mt-2 mb-6 max-w-2xl text-slate-600">
        Calcule cuántos tapetes y clavos necesita y cuánto cuestan. Agréguelos a su solicitud y le enviamos la cotización.
      </p>
      <MatCalculator mats={mats} nail={nail} />
    </main>
  );
}
