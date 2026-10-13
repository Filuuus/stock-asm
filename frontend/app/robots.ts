import type { MetadataRoute } from "next";

// Search engines index the catalog and product pages only; staff pages,
// the cart and customers' quote links stay out.
export default function robots(): MetadataRoute.Robots {
  const site = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";
  return {
    rules: {
      userAgent: "*",
      allow: ["/", "/producto/"],
      disallow: [
        "/carrito", "/solicitud/", "/solicitudes", "/fotos", "/comisiones", "/corte-de-caja", "/facturas",
        "/ventas", "/rentabilidad", "/usuarios", "/login",
      ],
    },
    sitemap: `${site}/sitemap.xml`,
  };
}
