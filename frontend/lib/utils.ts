import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// "$1,234.50" - every amount on screen goes through this.
export function formatMoney(value: number) {
  return value.toLocaleString("es-MX", {
    style: "currency",
    currency: "MXN",
    maximumFractionDigits: 2,
  });
}

// "1 factura", "3 facturas"
export function plural(n: number, one: string, many: string) {
  return `${n} ${n === 1 ? one : many}`;
}
