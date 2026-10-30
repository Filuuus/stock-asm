import { Skeleton } from "@/components/ui/skeleton";

// Shown at once while the catalog loads, so opening it never feels like a dead click.
export default function Loading() {
  return (
    <main className="flex flex-col md:flex-row max-w-7xl mx-auto w-full gap-4 md:gap-8 p-4 sm:p-6">
      <div className="hidden md:block w-64 flex-shrink-0 space-y-3">
        {Array.from({ length: 8 }, (_, i) => (
          <Skeleton key={i} className="h-5" />
        ))}
      </div>
      <div className="flex-1 grid grid-cols-2 content-start gap-3 sm:gap-4 lg:grid-cols-3 xl:grid-cols-4">
        {Array.from({ length: 12 }, (_, i) => (
          <div key={i} className="rounded-xl border border-gray-200 bg-white p-3 sm:p-4">
            <Skeleton className="aspect-square" />
            <Skeleton className="mt-3 h-4 w-3/4" />
            <Skeleton className="mt-2 h-4 w-1/2" />
          </div>
        ))}
      </div>
    </main>
  );
}
