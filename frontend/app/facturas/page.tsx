import { Suspense } from "react";
import FacturaView from "@/components/facturas/FacturaView";

// FacturaView reads ?q= and ?id= with useSearchParams, which needs a
// Suspense boundary to prerender the rest of the page.
export default function Page() {
  return (
    <Suspense>
      <FacturaView />
    </Suspense>
  );
}
