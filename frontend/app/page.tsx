import type { Metadata } from "next";
import LandingView from "@/components/landing/LandingView";
import { Coverage } from "@/components/landing/CoverageMap";
import { API_URL } from "@/lib/api";
import { Product } from "@/types/api";

export const metadata: Metadata = {
  description:
    "Equipo de ordeño GEA, higiene, tapetes, nutrición Bionat y ventilación en Los Altos de Jalisco, con servicio en ruta.",
};

// The public view (no cookie): the home page shows what any visitor would see. Rebuilt at most hourly.
async function getJson<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${API_URL}${path}`, { next: { revalidate: 3600 } });
    return res.ok ? res.json() : null;
  } catch {
    return null;
  }
}

export default async function Page() {
  const [products, coverage] = await Promise.all([
    getJson<Product[]>("/api/inventory/"),
    getJson<Coverage>("/api/profitability/coverage/"),
  ]);
  return <LandingView products={products ?? []} coverage={coverage} />;
}
