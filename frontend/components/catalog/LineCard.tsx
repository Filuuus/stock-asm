import Image from "next/image";
import Link from "next/link";
import { ProductLine } from "@/types/api";
import { formatMoney, productHref } from "@/lib/utils";

export function linePrice(line: ProductLine) {
  return line.price_from ? `Desde ${formatMoney(line.price_from)}` : "Se cotiza";
}

export const lineAvailability = (line: ProductLine) => (line.in_stock ? "Disponible" : "Sobre pedido");

export const lineImage = (line: ProductLine) => {
  const image = line.images.find((i) => i.is_primary) ?? line.images[0];
  return image ? `/products/${image.file}` : "/placeholder.svg";
};

// A whole product line, for the recommendations on a mat's page.
export default function LineCard({ line }: { line: ProductLine }) {
  const href = productHref(line.key, line.slug);
  return (
    <Link href={href} className="flex flex-col rounded-xl border border-gray-200 bg-white p-3 transition-shadow hover:shadow-md sm:p-4">
      <div className="relative aspect-square w-full overflow-hidden rounded-lg bg-gray-50">
        <Image src={lineImage(line)} alt={line.line} fill sizes="(min-width: 1024px) 20vw, 50vw" className="object-cover" />
      </div>
      <h3 className="mt-3 font-medium text-gray-900">{line.line}</h3>
      {line.versions > 1 && <p className="text-xs text-gray-500">{line.versions} opciones</p>}
      <p className="mt-1 text-sm font-semibold text-gray-900">{linePrice(line)}</p>
      <p className={`mt-0.5 text-xs font-medium ${line.in_stock ? "text-green-700" : "text-amber-700"}`}>{lineAvailability(line)}</p>
    </Link>
  );
}
