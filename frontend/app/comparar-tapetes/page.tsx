import type { Metadata } from "next";
import MatCompareView from "@/components/catalog/MatCompareView";
import { API_URL } from "@/lib/api";
import { getNail } from "@/lib/nail";
import { ProductLine } from "@/types/api";

export const metadata: Metadata = {
  title: "Compara tapetes y colchones para ganado",
  description: "Compara tapetes de hule y colchones Animat por espesor, superficie y uso, y elige el indicado para tu establo.",
};

// No cookie: everyone gets the public view. Live, so prices and stock match the product pages.
export default async function Page() {
  const res = await fetch(`${API_URL}/api/inventory/lineas/`, { cache: "no-store" }).catch(() => null);
  const lines: ProductLine[] = res?.ok ? await res.json() : [];
  return <MatCompareView lines={lines} nailPrice={(await getNail())?.price ?? null} />;
}
