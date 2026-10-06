import { format } from "date-fns";
import { es } from "date-fns/locale";

// Calendar dates travel as "YYYY-MM-DD" strings and months as "YYYY-MM".
//
// Built from parts, never parsed with new Date("YYYY-MM-DD") or
// date-fns's parseISO: those have produced a real off-by-one-day display
// bug here (a date stored as the 24th rendering as "23 sep"). And "today"
// is the LOCAL date - toISOString() is UTC, which in Mexico turns into
// tomorrow after 6 pm.

export function isoToDate(iso: string) {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, month - 1, day || 1);
}

export function dateToISO(date: Date) {
  return format(date, "yyyy-MM-dd");
}

export function todayISO() {
  return dateToISO(new Date());
}

export function monthToISO(date: Date) {
  return format(date, "yyyy-MM");
}

export function currentMonthISO() {
  return monthToISO(new Date());
}

// "18 sep 2026" - accepts a date or a datetime string.
export function formatDay(iso: string | null | undefined) {
  if (!iso) return "-";
  return format(isoToDate(iso.slice(0, 10)), "d MMM yyyy", { locale: es });
}

// "6 oct" - for date ranges within the next weeks.
export function formatDayShort(iso: string) {
  return format(isoToDate(iso.slice(0, 10)), "d MMM", { locale: es });
}

// "septiembre 2026"
export function formatMonth(month: string) {
  return format(isoToDate(month), "MMMM yyyy", { locale: es });
}
