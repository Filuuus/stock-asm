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
  images: ProductImage[];
  price_visible: boolean;
}
