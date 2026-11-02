import type { Metadata } from "next";
import MyRequestsView from "@/components/quote/MyRequestsView";

export const metadata: Metadata = { title: "Mis solicitudes | Agropecuaria Santa María", robots: { index: false, follow: false } };

export default function Page() {
  return <MyRequestsView />;
}
