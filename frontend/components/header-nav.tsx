"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { LogOut, Menu, ShoppingCart, User } from "lucide-react";
import { useCart } from "@/hooks/use-cart";
import { useAuth } from "@/hooks/use-auth";
import {
  Sheet,
  SheetContent,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

// Inline links on desktop; below that, one menu button that opens
// the same links in a side panel, so the header stays a single row.
export default function HeaderNav() {
  const router = useRouter();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const { user, loading, isAccounting, isManagement, logout } = useAuth();
  const { count } = useCart();

  const links = [
    { href: "/", label: "Catálogo", show: true },
    { href: "/solicitudes", label: "Solicitudes", show: !!user },
    { href: "/comisiones", label: "Comisiones", show: true },
    {
      href: "/corte-de-caja",
      label: "Corte de Caja",
      show: isAccounting || isManagement,
    },
    {
      href: "/facturas",
      label: "Facturas",
      show: isAccounting || isManagement,
    },
    { href: "/ventas", label: "Ventas", show: isManagement },
    { href: "/usuarios", label: "Usuarios", show: isManagement },
  ].filter((l) => l.show);

  const handleLogout = async () => {
    setOpen(false);
    await logout();
    router.push("/");
  };

  const linkClass = (href: string) =>
    cn(
      "text-sm font-medium whitespace-nowrap hover:text-white",
      pathname === href ? "text-white" : "text-slate-300",
    );

  return (
    <div className="flex items-center gap-x-5">
      {/* The quote-request cart, on every screen size. */}
      <Link
        href="/carrito"
        aria-label={`Mi solicitud (${count} productos)`}
        className="relative order-last p-2 -mr-2 rounded-md hover:bg-slate-800 lg:order-none lg:mr-0"
      >
        <ShoppingCart className="h-6 w-6" />
        {count > 0 && (
          <span className="absolute -right-0.5 -top-0.5 min-w-[1.25rem] rounded-full bg-blue-500 px-1 text-center text-xs font-semibold leading-5">
            {count}
          </span>
        )}
      </Link>
      <nav className="hidden lg:flex items-center gap-x-5">
        {links.map((l) => (
          <Link key={l.href} href={l.href} className={linkClass(l.href)}>
            {l.label}
          </Link>
        ))}
        {loading ? null : user ? (
          <div className="flex items-center gap-2">
            <span className="flex items-center gap-1.5 text-sm text-slate-300">
              <User className="w-4 h-4" />
              {user.username}
            </span>
            <button
              aria-label="Cerrar sesión"
              onClick={handleLogout}
              className="p-2 hover:bg-slate-800 rounded-full"
            >
              <LogOut className="w-5 h-5" />
            </button>
          </div>
        ) : (
          <Link href="/login" className={linkClass("/login")}>
            Iniciar sesión
          </Link>
        )}
      </nav>

      <Sheet open={open} onOpenChange={setOpen}>
        <SheetTrigger asChild>
          <button
            aria-label="Menú"
            className="lg:hidden p-2 -mr-2 hover:bg-slate-800 rounded-md"
          >
            <Menu className="w-6 h-6" />
          </button>
        </SheetTrigger>
        <SheetContent
          side="right"
          className="w-64 flex flex-col gap-1 bg-slate-900 text-white border-slate-800"
        >
          <SheetTitle className="text-white mb-4">Menú</SheetTitle>
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              onClick={() => setOpen(false)}
              className={cn(
                "rounded-md px-3 py-2.5 text-base font-medium",
                pathname === l.href
                  ? "bg-slate-800 text-white"
                  : "text-slate-300 hover:bg-slate-800",
              )}
            >
              {l.label}
            </Link>
          ))}
          <div className="mt-auto border-t border-slate-800 pt-4">
            {loading ? null : user ? (
              <div className="flex items-center justify-between px-3">
                <span className="flex items-center gap-1.5 text-sm text-slate-300">
                  <User className="w-4 h-4" />
                  {user.username}
                </span>
                <button
                  onClick={handleLogout}
                  className="flex items-center gap-1.5 rounded-md px-2 py-1.5 text-sm text-slate-300 hover:bg-slate-800"
                >
                  <LogOut className="w-4 h-4" />
                  Salir
                </button>
              </div>
            ) : (
              <Link
                href="/login"
                onClick={() => setOpen(false)}
                className="block rounded-md px-3 py-2.5 text-base font-medium text-slate-300 hover:bg-slate-800"
              >
                Iniciar sesión
              </Link>
            )}
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}
