export type Brand = "GEA" | "Bionat Sano" | "Animat" | "VES-Artex";

export type Category =
  | "Sistemas de Ordeño"
  | "Nutrición"
  | "Refacciones"
  | "Confort Animal"
  | "Almacenamiento";

export interface Product {
  id: string;
  brand: Brand;
  category: Category;
  name: string;
  sku: string;
  price: number;
  stock: number;
}

export const brandBadgeStyles: Record<Brand, string> = {
  GEA: "bg-blue-50 text-blue-700",
  "Bionat Sano": "bg-emerald-50 text-emerald-700",
  Animat: "bg-amber-50 text-amber-700",
  "VES-Artex": "bg-purple-50 text-purple-700",
};

export const categories: Category[] = [
  "Sistemas de Ordeño",
  "Nutrición",
  "Refacciones",
  "Confort Animal",
  "Almacenamiento",
];

export const brands: { name: Brand; count: number }[] = [
  { name: "GEA", count: 3 },
  { name: "Bionat Sano", count: 3 },
  { name: "Animat", count: 2 },
  { name: "VES-Artex", count: 2 },
];

export const products: Product[] = [
  {
    id: "7300-2680-120",
    brand: "GEA",
    category: "Sistemas de Ordeño",
    name: "Enfriador de Leche Tanque Vertical 2000L",
    sku: "7300-2680-120",
    price: 125000,
    stock: 3,
  },
  {
    id: "7300-4510-085",
    brand: "GEA",
    category: "Sistemas de Ordeño",
    name: "Bomba Centrífuga Sanitaria Acero Inox",
    sku: "7300-4510-085",
    price: 18750,
    stock: 12,
  },
  {
    id: "BN-2024-001",
    brand: "Bionat Sano",
    category: "Nutrición",
    name: "Suplemento Mineral Bovino Premium 25kg",
    sku: "BN-2024-001",
    price: 1250,
    stock: 45,
  },
  {
    id: "BN-2024-015",
    brand: "Bionat Sano",
    category: "Nutrición",
    name: "Desparasitante Inyectable Ganado 500ml",
    sku: "BN-2024-015",
    price: 890,
    stock: 28,
  },
  {
    id: "AN-8800-220",
    brand: "Animat",
    category: "Confort Animal",
    name: "Comedero Automático Ganado Bovino 300kg",
    sku: "AN-8800-220",
    price: 8500,
    stock: 7,
  },
  {
    id: "AN-8800-340",
    brand: "Animat",
    category: "Confort Animal",
    name: "Bebedero Automático Nivel Constante Acero",
    sku: "AN-8800-340",
    price: 4200,
    stock: 2,
  },
  {
    id: "VA-1100-050",
    brand: "VES-Artex",
    category: "Confort Animal",
    name: "Cepillo Rotatorio Automático para Vacas",
    sku: "VA-1100-050",
    price: 32000,
    stock: 1,
  },
  {
    id: "VA-1100-072",
    brand: "VES-Artex",
    category: "Confort Animal",
    name: "Colchoneta Cubículo Bovino 1.8m x 1.2m",
    sku: "VA-1100-072",
    price: 3800,
    stock: 35,
  },
  {
    id: "7300-6200-045",
    brand: "GEA",
    category: "Sistemas de Ordeño",
    name: "Filtro de Línea Leche Acero Inoxidable",
    sku: "7300-6200-045",
    price: 6500,
    stock: 18,
  },
  {
    id: "BN-2024-032",
    brand: "Bionat Sano",
    category: "Nutrición",
    name: "Vitamina ADE Inyectable Ganado 250ml",
    sku: "BN-2024-032",
    price: 300,
    stock: 4,
  },
];

export const LOW_STOCK_THRESHOLD = 5;

export function formatPrice(price: number) {
  return `$${price.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}
