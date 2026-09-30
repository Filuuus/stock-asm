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
  CTEXTOEXTRA1: string | null;
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
