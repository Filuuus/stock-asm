import { Check } from "lucide-react";
import { DescriptionBlock, parseDescription } from "@/lib/description";

function Block({ block, lead }: { block: DescriptionBlock; lead: boolean }) {
  switch (block.type) {
    case "text":
      return <p className={`whitespace-pre-line leading-relaxed ${lead ? "text-base text-gray-900" : "text-sm text-gray-700"}`}>{block.text}</p>;
    case "list":
      return (
        <ul className="grid gap-x-8 gap-y-2.5 md:grid-cols-2">
          {block.items.map((item) => (
            <li key={item} className="flex gap-2.5 text-sm leading-relaxed text-gray-700">
              <Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" aria-hidden />
              <span>{item}</span>
            </li>
          ))}
        </ul>
      );
    case "specs":
      return (
        <div>
          {block.title && <h3 className="mb-2 text-sm font-semibold text-gray-900">{block.title}</h3>}
          <dl className="overflow-hidden rounded-lg border border-gray-200 bg-white text-sm">
            {block.rows.map((r) => (
              <div key={r.label} className="grid gap-1 border-b border-gray-100 px-4 py-2 last:border-0 odd:bg-slate-50 sm:grid-cols-[11rem_1fr] sm:gap-4">
                <dt className="font-medium text-gray-900">{r.label}</dt>
                <dd className="text-gray-700 first-letter:uppercase">{r.value}</dd>
              </div>
            ))}
          </dl>
        </div>
      );
    case "note":
      return (
        <div>
          <h3 className="mb-1 text-sm font-semibold text-gray-900">{block.label}</h3>
          <p className="text-sm leading-relaxed text-gray-700">{block.text[0].toUpperCase() + block.text.slice(1)}</p>
        </div>
      );
  }
}

// The description laid out from the structure of its text.
export default function DescriptionBody({ text }: { text: string }) {
  const blocks = parseDescription(text);
  return (
    <div className="space-y-5">
      {blocks.map((block, i) => (
        <Block key={i} block={block} lead={i === 0 && block.type === "text"} />
      ))}
    </div>
  );
}
