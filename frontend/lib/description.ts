// A description is plain text staff can edit; this reads its structure back so the page can lay it out.
export type DescriptionBlock =
  | { type: "text"; text: string }
  | { type: "list"; items: string[] }
  | { type: "specs"; title?: string; rows: { label: string; value: string }[] }
  | { type: "note"; label: string; text: string };

const LABELLED = /^([A-ZÁÉÍÓÚÑ¿][^:.\n]{1,40}):\s+(.+)$/;

const row = (line: string) => {
  const m = line.match(LABELLED);
  return m ? { label: m[1], value: m[2] } : null;
};

function parseBlock(block: string): DescriptionBlock[] {
  const lines = block.split("\n").map((l) => l.trim()).filter(Boolean);
  const [first, ...rest] = lines;
  const rows = lines.map(row);
  const titled = rest.map(row);
  if (rest.length > 0 && !rows[0] && !first.startsWith("•") && titled.every(Boolean)) {
    return [{ type: "specs", title: first, rows: titled.flatMap((r) => (r ? [r] : [])) }];
  }
  if (lines.length > 1 && rows.every(Boolean)) return [{ type: "specs", rows: rows.flatMap((r) => (r ? [r] : [])) }];
  if (lines.length === 1 && rows[0]) return [{ type: "note", label: rows[0].label, text: rows[0].value }];

  const out: DescriptionBlock[] = [];
  for (const l of lines) {
    const last = out[out.length - 1];
    if (l.startsWith("•")) {
      const item = l.replace(/^•\s*/, "");
      if (last?.type === "list") last.items.push(item);
      else out.push({ type: "list", items: [item] });
    } else if (last?.type === "text") last.text += `\n${l}`;
    else out.push({ type: "text", text: l });
  }
  return out;
}

export const parseDescription = (text: string) => text.split(/\n\s*\n/).flatMap(parseBlock);

// One spec-sheet value, by its label.
export function specValue(blocks: DescriptionBlock[], label: string) {
  for (const b of blocks) {
    const hit = b.type === "specs" && b.rows.find((r) => r.label === label);
    if (hit) return hit.value;
  }
  return null;
}
