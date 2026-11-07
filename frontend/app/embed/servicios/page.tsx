import type { Metadata } from "next";
import ServicePlanView from "@/components/maintenance/ServicePlanView";

export const metadata: Metadata = { title: "Servicios", robots: { index: false, follow: false } };

// The Servicios view for a Notion /embed block (office only): no site header, Solicitudes as a tab, signed in with
// the link's key (?k=, see lib/api.ts and manage.py embed_link) because Notion's frame doesn't get our cookie.
export default function Page() {
  return <ServicePlanView embedded />;
}
