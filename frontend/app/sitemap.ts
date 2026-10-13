import type { MetadataRoute } from "next";
import { productHref } from "@/lib/utils";
import { API_URL } from "@/lib/api";
import { Product } from "@/types/api";

// Rebuilt at most hourly (stock changes what the public catalog lists).
export const revalidate = 3600;

// The catalog and every product the public can see (no cookie: the public view).
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const site = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";
  const res = await fetch(`${API_URL}/api/inventory/`, { next: { revalidate } });
  const products: Product[] = res.ok ? await res.json() : [];
  return [
    { url: site, changeFrequency: "daily", priority: 1 },
    ...products.map((p) => ({ url: `${site}${productHref(p.key, p.slug)}`, changeFrequency: "weekly" as const })),
  ];
}
