// Excludes visually ambiguous characters (0/O, 1/l/I) - these passwords are
// typically set up by an admin for someone else and read aloud or written
// on a sticky note, not typed by the account owner themselves.
const PASSWORD_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789";

export function generatePassword(length = 12): string {
  const values = new Uint32Array(length);
  crypto.getRandomValues(values);
  return Array.from(values, (v) => PASSWORD_CHARS[v % PASSWORD_CHARS.length]).join("");
}
