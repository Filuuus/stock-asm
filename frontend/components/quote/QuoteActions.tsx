"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Check, Copy, MessageCircle, Pencil, Phone, Printer } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useCart } from "@/hooks/use-cart";
import { setQuoteRevision } from "@/lib/quote-revision";
import { whatsappUrl } from "@/lib/quote-status";
import { rememberQuote } from "@/lib/saved-quotes";

interface Item {
  key: string | null;
  name: string;
  image: string | null;
  quantity: number;
}

interface Props {
  token: string;
  number: number;
  createdAt: string;
  items: Item[];
  approved: boolean;
  expired: boolean;
  canModify: boolean;
  contactPhone: string | null;
}

// Everything a customer can do from their quote: all of it ends in WhatsApp or the cart,
// because the sale itself is closed by staff in Contpaqi.
export default function QuoteActions({ token, number, createdAt, items, approved, expired, canModify, contactPhone }: Props) {
  const router = useRouter();
  const { items: cart, replace } = useCart();
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    rememberQuote({ token, number, created_at: createdAt, products: items.length });
  }, [token, number, createdAt, items.length]);

  const link = () => `${process.env.NEXT_PUBLIC_SITE_URL ?? window.location.origin}/solicitud/${token}`;
  const modify = () => {
    if (cart.length > 0 && !window.confirm("Esto reemplaza los productos que tienes en tu carrito. ¿Continuar?")) return;
    replace(items.flatMap((i) => (i.key ? [{ key: i.key, name: i.name, image: i.image, quantity: Number(i.quantity) }] : [])));
    setQuoteRevision({ token, number });
    router.push("/carrito");
  };

  return (
    <div className="mt-6 space-y-4 print:hidden">
      <div className="flex flex-wrap gap-2">
        {approved && !expired && contactPhone && (
          <Button asChild>
            <a href={whatsappUrl(contactPhone, `Hola, quiero avanzar con la cotización #${number}.`)} target="_blank" rel="noopener noreferrer">
              <MessageCircle className="mr-1.5 h-4 w-4" />
              Quiero avanzar con esta cotización
            </a>
          </Button>
        )}
        {canModify && (
          <Button variant={expired ? "default" : "outline"} onClick={modify}>
            <Pencil className="mr-1.5 h-4 w-4" />
            {expired ? "Solicitar actualización" : "Modificar solicitud"}
          </Button>
        )}
        {approved && (
          <Button variant="outline" onClick={() => window.print()}>
            <Printer className="mr-1.5 h-4 w-4" />
            Descargar PDF
          </Button>
        )}
      </div>

      {contactPhone && (
        <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-gray-600">
          ¿Dudas?
          <a href={`tel:${contactPhone}`} className="inline-flex items-center gap-1 text-blue-600 hover:underline">
            <Phone className="h-3.5 w-3.5" />
            {contactPhone}
          </a>
          <a
            href={whatsappUrl(contactPhone, `Hola, tengo una duda sobre la solicitud #${number}.`)}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-blue-600 hover:underline"
          >
            <MessageCircle className="h-3.5 w-3.5" />
            WhatsApp
          </a>
        </p>
      )}

      <div className="rounded-lg border border-gray-200 bg-white p-3 sm:p-4">
        <p className="text-sm font-medium text-gray-900">Guarda tu enlace</p>
        <p className="mt-0.5 text-sm text-gray-500">
          Con él puedes volver a esta página y ver cómo va tu solicitud. También queda en Mis solicitudes en este dispositivo.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => window.open(whatsappUrl("", `Mi solicitud #${number} de Agropecuaria Santa María: ${link()}`), "_blank", "noopener")}
          >
            <MessageCircle className="mr-1.5 h-4 w-4" />
            Enviármelo por WhatsApp
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={async () => {
              await navigator.clipboard.writeText(link());
              setCopied(true);
            }}
          >
            {copied ? <Check className="mr-1.5 h-4 w-4" /> : <Copy className="mr-1.5 h-4 w-4" />}
            {copied ? "Enlace copiado" : "Copiar enlace"}
          </Button>
        </div>
      </div>
    </div>
  );
}
