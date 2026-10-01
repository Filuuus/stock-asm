export interface ProductImage {
  file: string;
  is_primary: boolean;
}

export interface Product {
  CIDPRODUCTO: number;
  CCODIGOPRODUCTO: string;
  CNOMBREPRODUCTO: string;
  // null when the requester can't see this product's price (public/logged-out
  // visitor and the product isn't flagged public) - see price_visible.
  CPRECIO1: number | null;
  brand: string | null;
  // Commission category code (R, R_CHEM, B, ...) - see CATEGORY_LABELS.
  category: string;
  line: string | null;
  images: ProductImage[];
  price_visible: boolean;
  // Units in ALMACEN GENERAL; null for the public, who only get in_stock.
  stock: number | null;
  in_stock: boolean;
  // 1 = best seller over the last 12 months; null = no sales.
  sold_rank: number | null;
}

// What the product page gets for a related part we also sell.
export type ProductSummary = Pick<
  Product,
  "CCODIGOPRODUCTO" | "CNOMBREPRODUCTO" | "CPRECIO1" | "price_visible" | "in_stock" | "images"
> & { stock?: number | null };

export interface ServiceRule {
  hours: number | null; // working hours
  months: number | null; // or calendar time, whichever comes first
  action: string; // "reemplazar", "Verificar fisuras/desgaste", ...
}

export interface RelatedPart {
  pos?: string; // position on the parts list / drawing
  qty?: number;
  code: string; // GEA code
  desc: string; // GEA description
  ours: ProductSummary[]; // our products with that GEA code
}

// Product page: the catalog fields plus what GEA's dealer portal says about it.
export interface ProductDetail extends Product {
  // Our assemblies whose parts list includes this product.
  appears_in: { pos: string; qty: number; has_drawing: boolean; parent: ProductSummary }[];
  gea: {
    code: string;
    desc: string;
    parts: RelatedPart[];
    drawing: { img: string | null; hotspots: { pos: string; box: [number, number, number, number] }[] } | null;
    spare_parts: RelatedPart[];
    used_in: RelatedPart[];
    manuals: { code: string; lang: string }[]; // GEA document number per language
    // GEA's service interval: general rules, plus different ones inside specific assemblies.
    service: {
      rules: ServiceRule[];
      in_assemblies: (ServiceRule & RelatedPart)[];
    } | null;
    note: {
      text: string;
      not_orderable: boolean;
      replacement: string | null;
      replacement_ours: ProductSummary[]; // our products for the replacement code
    } | null; // staff only
  } | null;
}
