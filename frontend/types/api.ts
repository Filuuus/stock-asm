export interface ProductImage {
  file: string;
  is_primary: boolean;
}

export interface Product {
  CIDPRODUCTO: number;
  // The public id (URLs, cart, quotes). Part numbers are private to staff.
  key: string;
  // null for the public (owner, 2026-10-13: customers would buy it elsewhere).
  CCODIGOPRODUCTO: string | null;
  CNOMBREPRODUCTO: string;
  // null when the requester can't see this product's price (logged-out visitor
  // and a category whose prices are private) - see price_visible.
  CPRECIO1: number | null; // before IVA, as the ERP stores it
  price: number | null; // what the customer pays: CPRECIO1 plus the product's IVA (null when hidden)
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
  // Staff only: GEA no longer supplies it; null otherwise (and always for the public).
  discontinued?: { replacement: string | null } | null;
}

// What the product page gets for a related part we also sell.
export type ProductSummary = Pick<
  Product,
  "key" | "CCODIGOPRODUCTO" | "CNOMBREPRODUCTO" | "CPRECIO1" | "price" | "price_visible" | "in_stock" | "images"
> & { stock?: number | null };

export interface ServiceRule {
  hours: number | null; // working hours
  months: number | null; // or calendar time, whichever comes first
  action: string; // "reemplazar", "Verificar fisuras/desgaste", ...
}

export interface RelatedPart {
  pos?: string; // position on the parts list / drawing
  qty?: number;
  code: string | null; // GEA code; null for the public
  desc: string; // GEA description
  ours: ProductSummary[]; // our products with that GEA code
}

// Product page: the catalog fields plus what GEA's dealer portal says about it.
export interface ProductDetail extends Product {
  // Staff only (null for the public): live from the ERP.
  staff: {
    warehouses: { name: string; units: number }[]; // every warehouse holding stock, trucks included
    sold_12m: number; // units invoiced minus returned
    last_sale: string | null; // ISO date
  } | null;
  // Our assemblies whose parts list includes this product.
  appears_in: { pos: string; qty: number; has_drawing: boolean; parent: ProductSummary }[];
  gea: {
    code: string | null; // null for the public
    desc: string;
    parts: RelatedPart[];
    drawing: { img: string | null; hotspots: { pos: string; box: [number, number, number, number] }[] } | null;
    spare_parts: RelatedPart[];
    used_in: RelatedPart[];
    manuals: { code: string; lang: string }[]; // GEA document number per language; staff only
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
