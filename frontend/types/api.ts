export interface ProductImage {
  file: string;
  is_primary: boolean;
}

export interface Product {
  CIDPRODUCTO: number;
  CCODIGOPRODUCTO: string;
  CNOMBREPRODUCTO: string;
  CPRECIO1: number;
  CTEXTOEXTRA1: string | null;
  brand: string | null;
  images: ProductImage[];
}
