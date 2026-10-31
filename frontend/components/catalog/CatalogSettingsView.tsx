"use client";

import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import Link from "next/link";
import { Loader2, Plus } from "lucide-react";
import { Notice } from "@/components/notice";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { CATEGORY_LABELS } from "@/components/catalog/CatalogFilters";
import { useAuth } from "@/hooks/use-auth";
import { apiFetch } from "@/lib/api";
import { productHref } from "@/lib/utils";
import { CatalogRules, CategoryRuleRow } from "@/types/api";

const BASE = "/api/catalogo/ajustes/";
const ON_ORDER_OPTIONS = [
  { value: "NEVER", label: "Nunca" },
  { value: "ALWAYS", label: "Siempre" },
  { value: "IF_SOLD", label: "Si se vendió en 12 meses" },
];

function Section({ title, hint, children }: { title: string; hint: string; children: ReactNode }) {
  return (
    <section className="mt-8">
      <h2 className="text-lg font-semibold text-gray-900">{title}</h2>
      <p className="mb-3 text-sm text-gray-500">{hint}</p>
      {children}
    </section>
  );
}

// Saves when the field loses focus and the text changed; a refused save puts the old text back.
function SaveOnBlur({ value, label, onSave }: { value: string; label: string; onSave: (text: string) => Promise<boolean> }) {
  const [text, setText] = useState(value);
  return (
    <Input
      value={text}
      aria-label={label}
      onChange={(e) => setText(e.target.value)}
      onBlur={async () => {
        if (text.trim() !== value && !(await onSave(text))) setText(value);
      }}
    />
  );
}

export default function CatalogSettingsView() {
  const { loading: authLoading, isManagement } = useAuth();
  const [rules, setRules] = useState<CatalogRules | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newName, setNewName] = useState("");

  useEffect(() => {
    if (!isManagement) return;
    apiFetch(BASE)
      .then((res) => (res.ok ? res.json() : Promise.reject()))
      .then(setRules)
      .catch(() => setError("No se pudieron cargar los ajustes."));
  }, [isManagement]);

  const save = async (path: string, method: string, body: object) => {
    setError(null);
    const res = await apiFetch(BASE + path, { method, body: JSON.stringify(body) });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      setError(data.error ?? "No se pudo guardar.");
      return false;
    }
    setRules(data);
    return true;
  };

  const add = async (e: FormEvent) => {
    e.preventDefault();
    if (await save("especiales/", "POST", { name: newName })) setNewName("");
  };
  const setCategory = (row: CategoryRuleRow, change: Partial<CategoryRuleRow>) =>
    save(`categorias/${row.category}/`, "PUT", { ...row, ...change });

  if (authLoading) return null;
  if (!isManagement) {
    return (
      <main className="mx-auto w-full max-w-5xl p-6">
        <Notice tone="error" title="Esta página es solo para Gerencia." />
      </main>
    );
  }

  return (
    <main className="mx-auto w-full max-w-5xl p-4 sm:p-6">
      <h1 className="text-2xl font-semibold text-gray-900">Ajustes del catálogo</h1>
      <p className="mt-1 text-sm text-gray-500">Lo que cambies aquí se aplica de inmediato en el sitio público.</p>
      {error && (
        <div className="mt-4">
          <Notice tone="error" title={error} />
        </div>
      )}
      {!rules ? (
        !error && <Loader2 className="mt-8 h-5 w-5 animate-spin text-gray-400" />
      ) : (
        <>
          <Section
            title="Productos sobre pedido"
            hint="Productos que no están en Contpaqi. Se muestran como «Sobre pedido» y se cotizan. Ponles fotos en Fotos y la descripción en su página."
          >
            <form onSubmit={add} className="mb-3 flex max-w-xl gap-2">
              <Input
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Nombre del producto nuevo"
                aria-label="Nombre del producto nuevo"
              />
              <Button type="submit" disabled={!newName.trim()}>
                <Plus className="mr-1 h-4 w-4" /> Agregar
              </Button>
            </form>
            <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Nombre</TableHead>
                    <TableHead className="w-20 whitespace-nowrap text-center">Fotos</TableHead>
                    <TableHead className="w-24 whitespace-nowrap text-center">Público</TableHead>
                    <TableHead className="w-20" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rules.specials.map((p) => (
                    <TableRow key={p.key}>
                      <TableCell className="min-w-64">
                        <SaveOnBlur
                          key={p.name}
                          value={p.name}
                          label={`Nombre de ${p.name}`}
                          onSave={(name) => save(`especiales/${p.key}/`, "PATCH", { name })}
                        />
                      </TableCell>
                      <TableCell className="text-center">{p.photos}</TableCell>
                      <TableCell className="text-center">
                        <Switch
                          checked={!p.hidden}
                          aria-label={`Mostrar ${p.name} al público`}
                          onCheckedChange={(on) => save(`ocultos/${p.key}/`, "PUT", { hidden: !on })}
                        />
                      </TableCell>
                      <TableCell>
                        <Link href={productHref(p.key, p.slug)} className="text-sm text-blue-600 hover:underline">
                          Ver
                        </Link>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </Section>

          <Section
            title="Productos ocultos"
            hint="Productos de Contpaqi que el público no ve. Para ocultar otro, entra a su página y apaga «Visible al público»."
          >
            <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
              {rules.hidden.length === 0 && <p className="p-4 text-sm text-gray-500">No hay productos ocultos.</p>}
              {rules.hidden.map((p) => (
                <div key={p.key} className="flex items-center gap-3 border-b border-gray-100 px-4 py-2 text-sm last:border-0">
                  {p.slug ? (
                    <Link href={productHref(p.key, p.slug)} className="min-w-0 flex-1 text-blue-600 hover:underline">
                      {p.name}
                    </Link>
                  ) : (
                    <span className="min-w-0 flex-1 text-gray-700">{p.name}</span>
                  )}
                  <Button variant="outline" size="sm" onClick={() => save(`ocultos/${p.key}/`, "PUT", { hidden: false })}>
                    Mostrar
                  </Button>
                </div>
              ))}
            </div>
          </Section>

          <Section title="Categorías" hint="Qué ve el público de cada categoría.">
            <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Categoría</TableHead>
                    <TableHead className="text-center">Mostrar precio</TableHead>
                    <TableHead>Sobre pedido sin existencia</TableHead>
                    <TableHead className="text-center">Mostrar marca</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rules.categories.map((row) => {
                    const label = CATEGORY_LABELS[row.category] ?? row.category;
                    return (
                      <TableRow key={row.category}>
                        <TableCell className="font-medium">{label}</TableCell>
                        <TableCell className="text-center">
                          <Switch
                            checked={row.show_price}
                            aria-label={`Mostrar precio de ${label}`}
                            onCheckedChange={(show_price) => setCategory(row, { show_price })}
                          />
                        </TableCell>
                        <TableCell>
                          <select
                            value={row.on_order}
                            aria-label={`Sobre pedido en ${label}`}
                            onChange={(e) => setCategory(row, { on_order: e.target.value as CategoryRuleRow["on_order"] })}
                            className="rounded-md border border-gray-300 bg-white px-2 py-1.5 text-sm"
                          >
                            {ON_ORDER_OPTIONS.map((o) => (
                              <option key={o.value} value={o.value}>
                                {o.label}
                              </option>
                            ))}
                          </select>
                        </TableCell>
                        <TableCell className="text-center">
                          <Switch
                            checked={!row.hide_brand}
                            aria-label={`Mostrar marca de ${label}`}
                            onCheckedChange={(on) => setCategory(row, { hide_brand: !on })}
                          />
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          </Section>

          <Section
            title="Marcas"
            hint="El nombre que ve el público. Deja vacío para no mostrar la marca, por ejemplo si es un distribuidor."
          >
            <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Marca en Contpaqi</TableHead>
                    <TableHead className="w-72">Nombre público</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rules.brands.map((b) => (
                    <TableRow key={b.erp_name}>
                      <TableCell className="text-sm">{b.erp_name}</TableCell>
                      <TableCell>
                        <SaveOnBlur
                          key={b.public_name}
                          value={b.public_name}
                          label={`Nombre público de ${b.erp_name}`}
                          onSave={(public_name) => save("marcas/", "PUT", { erp_name: b.erp_name, public_name })}
                        />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </Section>
        </>
      )}
    </main>
  );
}
