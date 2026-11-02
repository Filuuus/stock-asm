// Product names are singular and uppercase ("TAPETE"); people search "tapetes". Every word has to
// be in the text, in any order, as written or as its singular. Both must already be normalized.
export function matchesQuery(text: string, query: string) {
  return query.split(/\s+/).filter(Boolean).every((word) => {
    const forms = [word];
    if (word.length > 3 && word.endsWith("s")) forms.push(word.slice(0, -1));
    if (word.length > 4 && word.endsWith("es")) forms.push(word.slice(0, -2));
    return forms.some((form) => text.includes(form));
  });
}
