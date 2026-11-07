"use client";

import type { ComponentProps } from "react";
import { whatsappUrl } from "@/lib/quote-status";

// A link that opens a WhatsApp chat: the address (web or app) is picked on click, in the browser, because the server
// can't tell a computer from a phone. Works inside <Button asChild>.
export function WhatsAppLink({ phone, text, disabled, onClick, className, ...props }:
  ComponentProps<"a"> & { phone: string; text?: string; disabled?: boolean }) {
  return (
    <a
      {...props}
      aria-disabled={disabled || undefined}
      className={disabled ? `${className ?? ""} pointer-events-none opacity-50` : className}
      href={`https://wa.me/${phone.replace(/\D/g, "")}`}
      target="_blank"
      rel="noopener noreferrer"
      onClick={(e) => {
        e.preventDefault();
        if (disabled) return;
        window.open(whatsappUrl(phone, text), "_blank", "noopener");
        onClick?.(e);
      }}
    />
  );
}
