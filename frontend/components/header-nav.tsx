"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { LogOut, User } from "lucide-react";
import { useAuth } from "@/hooks/use-auth";

export default function HeaderNav() {
  const router = useRouter();
  const { user, loading, isAccounting, isManagement, logout } = useAuth();

  const handleLogout = async () => {
    await logout();
    router.push("/");
  };

  return (
    <>
      <Link
        href="/comisiones"
        className="text-sm font-medium text-slate-200 hover:text-white"
      >
        Comisiones
      </Link>
      {(isAccounting || isManagement) && (
        <Link
          href="/corte-de-caja"
          className="text-sm font-medium text-slate-200 hover:text-white"
        >
          Corte de Caja
        </Link>
      )}
      {isManagement && (
        <Link
          href="/usuarios"
          className="text-sm font-medium text-slate-200 hover:text-white"
        >
          Usuarios
        </Link>
      )}
      {!loading && user ? (
        <div className="flex items-center gap-2">
          <span className="flex items-center gap-1.5 text-sm text-slate-200">
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
        <Link
          href="/login"
          className="text-sm font-medium text-slate-200 hover:text-white"
        >
          Iniciar sesión
        </Link>
      )}
    </>
  );
}
