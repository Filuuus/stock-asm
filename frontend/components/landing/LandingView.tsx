import Image from "next/image";
import Link from "next/link";
import { ChevronRight, MapPin, PackageCheck, Truck, Wrench } from "lucide-react";
import CoverageMap, { Coverage } from "@/components/landing/CoverageMap";
import { Product } from "@/types/api";

// Draft copy (2026-10-15): written from what the business does today, pending management's review.
// The order follows the social-media proposal: promise, route service, solutions, how to quote.

const ADDRESS = "Av. Guadalajara 135-A, Col. Españita, Tepatitlán de Morelos, Jal., C.P. 47630";
// Office contact as published on the company's previous site (agrostma.com.mx).
const PHONES = ["378 782 27 68", "378 782 32 18"];
const EMAIL = "contacto@agrostma.com.mx";
const SOCIAL = [
  { label: "Facebook", href: "https://www.facebook.com/agropecuaria.santamariasadecv.9" },
  { label: "Instagram", href: "https://www.instagram.com/agrostmaria/" },
];
const LINK = "text-emerald-400 hover:underline";

// Each one opens the catalog filtered to its category; the id is the anchor ads can link to.
const SOLUTIONS = [
  {
    id: "ordeno",
    category: "R",
    photo: "PEZONERA", // the picture comes from a best seller whose name has this
    title: "Equipo y refacciones de ordeño GEA",
    text: "Pezoneras, pulsadores, mangueras y refacciones originales en existencia, para que su sala no pare.",
  },
  {
    id: "higiene",
    category: "R_CHEM",
    photo: "SELLADOR",
    title: "Higiene de ordeño",
    text: "Selladores, detergentes y desinfectantes para la rutina de ordeño y la limpieza del equipo.",
  },
  {
    id: "tapetes",
    category: "R_NW",
    photo: "TAPETE",
    title: "Tapetes de hule North West Rubber",
    text: "Tapetes para echaderos, pasillos y becerras, que ayudan a cuidar las pezuñas. Los instalamos en su establo.",
  },
  {
    id: "nutricion",
    category: "B",
    photo: "",
    title: "Nutrición animal Bionat",
    text: "Sustitutos de leche, minerales, premezclas y aditivos para becerras y ganado en producción.",
  },
  {
    id: "ventilacion",
    category: "R_FAN",
    photo: "VENTILADOR",
    title: "Ventilación para establos",
    text: "Ventiladores VES-Artex y GEA, con refacciones, para bajar el estrés por calor de sus vacas.",
  },
];

const ROUTE_FACTS = [
  { icon: Truck, text: "Dos rutas con vendedor y camioneta propia" },
  { icon: MapPin, text: "Entrega en su rancho, dentro de la zona" },
  { icon: Wrench, text: "Instalación de tapetes en su establo" },
  { icon: PackageCheck, text: "Refacciones en existencia en Tepatitlán" },
];

const STEPS = [
  { title: "Elija sus productos", text: "Vea precios y existencia en el catálogo y agréguelos a su solicitud." },
  { title: "Envíe su solicitud", text: "Solo su nombre y teléfono. No tiene costo ni compromiso." },
  { title: "Le enviamos su cotización", text: "Revisamos su pedido y le respondemos con precios y entrega." },
];

const BUTTON = "inline-flex items-center justify-center gap-1.5 rounded-lg px-5 py-3 text-base font-semibold";

function catalogHref(category: string) {
  return `/catalogo?${new URLSearchParams({ categoria: category })}`;
}

// The card's picture: the best seller with a photo among the products named like the solution.
function summarize(products: Product[], category: string, word: string) {
  const own = products.filter((p) => p.category === category);
  const byRank = (p: Product) => p.sold_rank ?? Infinity;
  const photo = own
    .filter((p) => p.images.length && p.CNOMBREPRODUCTO.toUpperCase().includes(word))
    .sort((a, b) => byRank(a) - byRank(b))[0];
  const image = photo && (photo.images.find((i) => i.is_primary) ?? photo.images[0]).file;
  return { count: own.length, image };
}

export default function LandingView({ products, coverage }: { products: Product[]; coverage: Coverage | null }) {
  return (
    <main className="w-full">
      <section className="bg-slate-900 text-white">
        <div className="mx-auto max-w-5xl px-4 py-14 sm:px-6 sm:py-20 text-center">
          <h1 className="text-3xl font-bold leading-tight sm:text-5xl">
            Todo para su establo, y se lo llevamos hasta su rancho
          </h1>
          <p className="mx-auto mt-4 max-w-2xl text-base text-slate-300 sm:text-lg">
            Equipo de ordeño, higiene, tapetes, nutrición y ventilación en Los Altos de Jalisco. Consulte precios en
            línea y pida su cotización sin compromiso.
          </p>
          <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row">
            <Link href="/catalogo" className={`${BUTTON} bg-emerald-500 text-white hover:bg-emerald-400`}>
              Ver catálogo y precios
              <ChevronRight className="h-5 w-5" />
            </Link>
            <a href="#cotizar" className={`${BUTTON} border border-slate-600 text-white hover:bg-slate-800`}>
              ¿Cómo cotizar?
            </a>
          </div>
        </div>
      </section>

      {coverage && coverage.cells.length > 0 && (
        <section id="ruta" className="mx-auto grid max-w-6xl items-center gap-8 px-4 py-14 sm:px-6 md:grid-cols-2">
          <div>
            <h2 className="text-2xl font-bold text-slate-900 sm:text-3xl">Servicio en ruta</h2>
            <p className="mt-3 text-slate-600">
              Nuestras rutas recorren Los Altos de Jalisco y alrededores. Lo verde es donde ya atendemos establos.
            </p>
            <ul className="mt-6 space-y-3">
              {ROUTE_FACTS.map(({ icon: Icon, text }) => (
                <li key={text} className="flex items-center gap-3 text-slate-800">
                  <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-emerald-100 text-emerald-700">
                    <Icon className="h-5 w-5" />
                  </span>
                  {text}
                </li>
              ))}
            </ul>
          </div>
          <CoverageMap coverage={coverage} />
        </section>
      )}

      <section id="soluciones" className="bg-white py-14">
        <div className="mx-auto max-w-5xl px-4 sm:px-6">
          <h2 className="text-2xl font-bold text-slate-900 sm:text-3xl">¿Qué necesita su establo?</h2>
          <div className="mt-6 space-y-4">
            {SOLUTIONS.map((s) => {
              const { count, image } = summarize(products, s.category, s.photo);
              return (
                <Link
                  key={s.id}
                  id={s.id}
                  href={catalogHref(s.category)}
                  className="group flex scroll-mt-4 items-center gap-4 rounded-xl border border-gray-200 p-3 transition-shadow hover:shadow-md sm:gap-6 sm:p-4"
                >
                  <div className="relative aspect-square w-20 flex-shrink-0 overflow-hidden rounded-lg bg-gray-50 sm:w-28">
                    <Image
                      src={image ? `/products/${image}` : "/placeholder.svg"}
                      alt=""
                      fill
                      sizes="112px"
                      className="object-cover"
                    />
                  </div>
                  <div className="min-w-0 flex-1">
                    <h3 className="font-semibold text-slate-900 sm:text-lg">{s.title}</h3>
                    <p className="mt-1 text-sm text-slate-600 sm:text-base">{s.text}</p>
                    <p className="mt-2 text-sm font-medium text-emerald-700">
                      Ver {count} productos
                    </p>
                  </div>
                  <ChevronRight className="h-6 w-6 flex-shrink-0 text-slate-400 group-hover:text-emerald-600" />
                </Link>
              );
            })}
          </div>
        </div>
      </section>

      <section id="cotizar" className="mx-auto max-w-5xl scroll-mt-4 px-4 py-14 sm:px-6">
        <h2 className="text-2xl font-bold text-slate-900 sm:text-3xl">¿Cómo cotizar?</h2>
        <ol className="mt-6 grid gap-4 sm:grid-cols-3">
          {STEPS.map((step, i) => (
            <li key={step.title} className="rounded-xl border border-gray-200 bg-white p-5">
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-emerald-500 font-bold text-white">
                {i + 1}
              </span>
              <h3 className="mt-3 font-semibold text-slate-900">{step.title}</h3>
              <p className="mt-1 text-sm text-slate-600">{step.text}</p>
            </li>
          ))}
        </ol>
        <div className="mt-8 flex flex-col items-start gap-6 rounded-xl bg-slate-900 p-6 text-white sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="font-semibold">Visítenos en Tepatitlán</p>
            <p className="mt-1 text-sm text-slate-300">{ADDRESS}</p>
            <a
              href={`https://www.google.com/maps/search/?${new URLSearchParams({ api: "1", query: ADDRESS })}`}
              target="_blank"
              rel="noopener noreferrer"
              className={`mt-1 inline-block text-sm ${LINK}`}
            >
              Cómo llegar
            </a>
            <p className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-sm">
              {PHONES.map((phone) => (
                <a key={phone} href={`tel:+52${phone.replace(/\s/g, "")}`} className={LINK}>
                  {phone}
                </a>
              ))}
              <a href={`mailto:${EMAIL}`} className={LINK}>
                {EMAIL}
              </a>
            </p>
            <p className="mt-1 flex gap-4 text-sm">
              {SOCIAL.map((s) => (
                <a key={s.label} href={s.href} target="_blank" rel="noopener noreferrer" className={LINK}>
                  {s.label}
                </a>
              ))}
            </p>
          </div>
          <Link href="/catalogo" className={`${BUTTON} flex-shrink-0 bg-emerald-500 text-white hover:bg-emerald-400`}>
            Empezar mi cotización
            <ChevronRight className="h-5 w-5" />
          </Link>
        </div>
      </section>
    </main>
  );
}
