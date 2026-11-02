import type { Metadata } from "next";
import LandingView from "@/components/landing/LandingView";
import { Coverage } from "@/components/landing/CoverageMap";
import { API_URL } from "@/lib/api";
import { Product } from "@/types/api";

export const metadata: Metadata = {
  title: "Equipo de ordeño GEA en Los Altos de Jalisco | Agropecuaria Santa María",
  description:
    "Equipo de ordeño GEA, higiene, tapetes, nutrición Bionat y ventilación en Los Altos de Jalisco, con servicio en ruta.",
};

// schema.org LocalBusiness: keep it the same as the Google Maps listing.
function jsonLd(siteUrl: string) {
  const weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"];
  return {
    "@context": "https://schema.org",
    "@type": "LocalBusiness",
    name: "Agropecuaria Santa María",
    url: siteUrl,
    logo: `${siteUrl}/logo.png`,
    image: `${siteUrl}/logo.png`,
    telephone: "+523787823218",
    address: {
      "@type": "PostalAddress",
      streetAddress: "Blvd. Anacleto Glez Flores Nte. 135, Españita",
      addressLocality: "Tepatitlán de Morelos",
      addressRegion: "Jalisco",
      postalCode: "47630",
      addressCountry: "MX",
    },
    geo: { "@type": "GeoCoordinates", latitude: 20.821079, longitude: -102.75134 },
    hasMap: "https://maps.app.goo.gl/V35sDWA6WD1btz7n7",
    areaServed: "Los Altos de Jalisco",
    openingHoursSpecification: [
      { "@type": "OpeningHoursSpecification", dayOfWeek: [...weekdays, "Saturday"], opens: "08:00", closes: "14:00" },
      { "@type": "OpeningHoursSpecification", dayOfWeek: weekdays, opens: "16:00", closes: "18:00" },
    ],
  };
}

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
  const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";
  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd(siteUrl)) }} />
      <LandingView products={products ?? []} coverage={coverage} />
    </>
  );
}
