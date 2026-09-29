"use client";

import { useState } from "react";
import { addDays, format, isSameDay } from "date-fns";
import { es } from "date-fns/locale";
import type { DateRange } from "react-day-picker";
import { Calendar as CalendarIcon, ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import { currentMonthISO, dateToISO, formatDay, formatMonth, isoToDate, monthToISO } from "@/lib/dates";

// The platform's date pickers: one look for all of them - an outline button
// with a calendar icon that opens a popover, with quick presets.

// A single trigger that opens a range-capable calendar (pick one day, or
// drag/click a start and end) - replaces two separate <input type="date">
// fields, which needed two round trips to change one day.
export function DateRangeControl({
  dateFrom,
  dateTo,
  onChange,
}: {
  dateFrom: string;
  dateTo: string;
  onChange: (from: string, to: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState<DateRange | undefined>({
    from: isoToDate(dateFrom),
    to: isoToDate(dateTo),
  });

  const handleOpenChange = (next: boolean) => {
    if (next) {
      setPending({ from: isoToDate(dateFrom), to: isoToDate(dateTo) });
    }
    setOpen(next);
  };

  const applyPreset = (from: Date, to: Date) => {
    onChange(dateToISO(from), dateToISO(to));
    setOpen(false);
  };

  const handleApply = () => {
    if (!pending?.from) return;
    applyPreset(pending.from, pending.to ?? pending.from);
  };

  const label = isSameDay(isoToDate(dateFrom), isoToDate(dateTo))
    ? formatDay(dateFrom)
    : `${formatDay(dateFrom)} – ${formatDay(dateTo)}`;

  return (
    <Popover open={open} onOpenChange={handleOpenChange}>
      <PopoverTrigger asChild>
        <Button variant="outline" className="w-56 justify-start gap-2 font-normal">
          <CalendarIcon className="w-4 h-4 text-gray-400" />
          {label}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-3" align="start">
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-2">
            <Button size="sm" variant="outline" onClick={() => applyPreset(new Date(), new Date())}>
              Hoy
            </Button>
            <Button size="sm" variant="outline" onClick={() => applyPreset(addDays(new Date(), -1), addDays(new Date(), -1))}>
              Ayer
            </Button>
          </div>
          <Calendar
            mode="range"
            selected={pending}
            onSelect={setPending}
            defaultMonth={pending?.to ?? pending?.from}
            numberOfMonths={2}
            locale={es}
          />
          <div className="flex items-center justify-between">
            <p className="text-xs text-gray-500">
              {pending?.from ? formatDay(dateToISO(pending.from)) : "Seleccione una fecha"}
              {pending?.to && !isSameDay(pending.from!, pending.to) ? ` – ${formatDay(dateToISO(pending.to))}` : ""}
            </p>
            <Button size="sm" onClick={handleApply} disabled={!pending?.from}>
              Aplicar
            </Button>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}

// A month picker in the same style: previous/next arrows around a button that
// opens a year with its twelve months. Months after the current one can't be
// picked - there is nothing to show for them yet.
export function MonthControl({
  month,
  onChange,
}: {
  month: string; // "YYYY-MM"
  onChange: (month: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [year, setYear] = useState(() => isoToDate(month).getFullYear());
  const current = currentMonthISO();
  const shift = (delta: number) => {
    const d = isoToDate(month);
    onChange(monthToISO(new Date(d.getFullYear(), d.getMonth() + delta, 1)));
  };
  const pick = (value: string) => {
    onChange(value);
    setOpen(false);
  };

  return (
    <div className="flex items-center gap-2">
      <Button size="icon" variant="outline" onClick={() => shift(-1)} title="Mes anterior">
        <ChevronLeft className="w-4 h-4" />
      </Button>
      <Popover
        open={open}
        onOpenChange={(next) => {
          if (next) setYear(isoToDate(month).getFullYear());
          setOpen(next);
        }}
      >
        <PopoverTrigger asChild>
          <Button variant="outline" className="w-56 justify-start gap-2 font-normal capitalize">
            <CalendarIcon className="w-4 h-4 text-gray-400" />
            {formatMonth(month)}
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-72 p-3" align="start">
          <div className="flex flex-col gap-3">
            <div className="flex items-center gap-2">
              <Button size="sm" variant="outline" onClick={() => pick(current)}>
                Este mes
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => pick(monthToISO(addDays(isoToDate(current), -1)))}
              >
                Mes anterior
              </Button>
            </div>
            <div className="flex items-center justify-between">
              <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => setYear((y) => y - 1)} title="Año anterior">
                <ChevronLeft className="w-4 h-4" />
              </Button>
              <span className="text-sm font-medium">{year}</span>
              <Button
                size="icon"
                variant="ghost"
                className="h-7 w-7"
                onClick={() => setYear((y) => y + 1)}
                disabled={year >= isoToDate(current).getFullYear()}
                title="Año siguiente"
              >
                <ChevronRight className="w-4 h-4" />
              </Button>
            </div>
            <div className="grid grid-cols-3 gap-1">
              {Array.from({ length: 12 }, (_, i) => {
                const value = monthToISO(new Date(year, i, 1));
                return (
                  <Button
                    key={value}
                    size="sm"
                    variant={value === month ? "default" : "ghost"}
                    disabled={value > current}
                    onClick={() => pick(value)}
                    className={cn("capitalize", value === current && value !== month && "font-semibold")}
                  >
                    {format(new Date(year, i, 1), "MMM", { locale: es }).replace(".", "")}
                  </Button>
                );
              })}
            </div>
          </div>
        </PopoverContent>
      </Popover>
      <Button size="icon" variant="outline" onClick={() => shift(1)} disabled={month >= current} title="Mes siguiente">
        <ChevronRight className="w-4 h-4" />
      </Button>
    </div>
  );
}
