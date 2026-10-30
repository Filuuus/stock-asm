"use client";

import { Fragment, useEffect, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ChevronDown, LogOut, Menu, ShoppingCart, User } from "lucide-react";
import { useCart } from "@/hooks/use-cart";
import { useAuth } from "@/hooks/use-auth";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Sheet,
  SheetContent,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { apiFetch } from "@/lib/api";
import { cn } from "@/lib/utils";

// Logged-out visitors get one row. Logged-in staff get a second row of links, split into groups,
// which is why this renders two direct children of the <header>. Below desktop, one menu button
// opens the same links in a side panel.
export default function HeaderNav() {
  const router = useRouter();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const { user, loading, isAccounting, isManagement, logout } = useAuth();
  const { count } = useCart();
  const staffSite = useIsStaffSite();
  const staff = !!user && staffSite;
  const pending = usePendingRequests(staff, pathname);

  const groups = [
    {
      label: "Ventas y clientes",
      links: [
        { href: "/solicitudes", label: "Solicitudes", show: staff, badge: pending },
        { href: "/catalogo", label: "Catálogo", show: true },
        { href: "/fotos", label: "Fotos", show: staff },
      ],
    },
    {
      label: "Administración",
      links: [
        { href: "/corte-de-caja", label: "Corte de Caja", show: staff && (isAccounting || isManagement) },
        { href: "/facturas", label: "Facturas", show: staff && (isAccounting || isManagement) },
        // A salesperson without a zone has no commissions to see (the server refuses them too).
        { href: "/comisiones", label: "Comisiones", show: staff && (isAccounting || isManagement || !!user.zone) },
      ],
    },
    {
      label: "Análisis",
      links: [
        { href: "/ventas", label: "Ventas", show: staff && isManagement },
        { href: "/rentabilidad", label: "Rentabilidad", show: staff && isManagement },
      ],
    },
  ]
    .map((g) => ({ ...g, links: g.links.filter((l) => l.show) }))
    .filter((g) => g.links.length > 0);

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

  const sheetLinkClass = (href: string) =>
    cn(
      "flex items-center justify-between rounded-md px-3 py-2.5 text-base font-medium",
      pathname === href ? "bg-slate-800 text-white" : "text-slate-300 hover:bg-slate-800",
    );

  return (
    <>
      <div className="flex items-center gap-x-5">
        {!staff && (
          <Link href="/catalogo" className={cn(linkClass("/catalogo"), "hidden lg:block")}>
            Catálogo
          </Link>
        )}
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
        {staff ? (
          <div className="hidden lg:block">
            <DropdownMenu>
              <DropdownMenuTrigger className="flex items-center gap-1.5 whitespace-nowrap rounded-md p-2 text-sm text-slate-300 hover:bg-slate-800 hover:text-white">
                <User className="w-4 h-4" />
                {user.username}
                <ChevronDown className="w-4 h-4" />
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                {isManagement && (
                  <DropdownMenuItem asChild>
                    <Link href="/usuarios">Usuarios</Link>
                  </DropdownMenuItem>
                )}
                <DropdownMenuItem onSelect={handleLogout}>
                  <LogOut className="w-4 h-4" />
                  Cerrar sesión
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        ) : (
          !loading &&
          staffSite && (
            <Link href="/login" className={cn(linkClass("/login"), "hidden lg:block")}>
              Iniciar sesión
            </Link>
          )
        )}

        <Sheet open={open} onOpenChange={setOpen}>
          <SheetTrigger asChild>
            <button
              aria-label="Menú"
              className="relative lg:hidden p-2 -mr-2 hover:bg-slate-800 rounded-md"
            >
              <Menu className="w-6 h-6" />
              {!!pending && <span className="absolute right-1 top-1 h-2.5 w-2.5 rounded-full bg-amber-400" />}
            </button>
          </SheetTrigger>
          <SheetContent
            side="right"
            className="w-64 flex flex-col gap-1 overflow-y-auto bg-slate-900 text-white border-slate-800"
          >
            <SheetTitle className="text-white mb-4">Menú</SheetTitle>
            {groups.map((g) => (
              <Fragment key={g.label}>
                {staff && <p className="px-3 pt-3 pb-1 text-xs text-slate-400">{g.label}</p>}
                {g.links.map((l) => (
                  <Link key={l.href} href={l.href} onClick={() => setOpen(false)} className={sheetLinkClass(l.href)}>
                    {l.label}
                    <Badge count={l.badge} />
                  </Link>
                ))}
              </Fragment>
            ))}
            <div className="mt-auto border-t border-slate-800 pt-4">
              {staff ? (
                <>
                  {isManagement && (
                    <Link href="/usuarios" onClick={() => setOpen(false)} className={sheetLinkClass("/usuarios")}>
                      Usuarios
                    </Link>
                  )}
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
                </>
              ) : (
                !loading &&
                staffSite && (
                  <Link href="/login" onClick={() => setOpen(false)} className={sheetLinkClass("/login")}>
                    Iniciar sesión
                  </Link>
                )
              )}
            </div>
          </SheetContent>
        </Sheet>
      </div>

      {staff && (
        <nav className="hidden lg:flex order-last w-full items-center gap-x-5 border-t border-slate-800 pt-2 -mb-1">
          {groups.map((g, i) => (
            <Fragment key={g.label}>
              {i > 0 && <span aria-hidden className="h-4 w-px bg-slate-600" />}
              {g.links.map((l) => (
                <Link
                  key={l.href}
                  href={l.href}
                  aria-current={pathname === l.href ? "page" : undefined}
                  className={cn(
                    linkClass(l.href),
                    "flex items-center gap-1.5 border-b-2 py-0.5",
                    pathname === l.href ? "border-blue-400" : "border-transparent",
                  )}
                >
                  {l.label}
                  <Badge count={l.badge} />
                </Link>
              ))}
            </Fragment>
          ))}
        </nav>
      )}
    </>
  );
}

// False on the public domain (NEXT_PUBLIC_SITE_URL, with or without www), where nginx closes the staff
// pages and login; true on the office address and in dev. False while server-rendering, so the public
// site never flashes the staff links before hydration.
function useIsStaffSite() {
  return useSyncExternalStore(noSubscribe, isStaffHost, () => false);
}

const noSubscribe = () => () => {};

function isStaffHost() {
  const site = process.env.NEXT_PUBLIC_SITE_URL;
  const publicHost = site ? new URL(site).hostname : null;
  const host = window.location.hostname;
  return host !== publicHost && host !== `www.${publicHost}`;
}

// New quote requests from the public site, so staff notice them without opening
// /solicitudes: re-checked every minute, on every page change and when the tab
// gets focus again (the person may have left it open all day).
function usePendingRequests(enabled: boolean, pathname: string) {
  const [pending, setPending] = useState(0);
  useEffect(() => {
    if (!enabled) return;
    const check = () =>
      apiFetch("/api/solicitudes/pendientes/")
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => d && setPending(d.nuevas))
        .catch(() => {});
    check();
    const timer = setInterval(check, 60_000);
    window.addEventListener("focus", check);
    return () => {
      clearInterval(timer);
      window.removeEventListener("focus", check);
    };
  }, [enabled, pathname]);
  return enabled ? pending : 0;
}

function Badge({ count }: { count?: number }) {
  if (!count) return null;
  return (
    <span
      aria-label={`${count} nuevas`}
      className="min-w-[1.25rem] rounded-full bg-amber-400 px-1.5 text-center text-xs font-semibold leading-5 text-slate-900"
    >
      {count}
    </span>
  );
}
