"use client";

import { use } from "react";
import RequestDetail from "@/components/quote/RequestDetail";

export default function RequestDetailPage({ params }: { params: Promise<{ id: string }> }) {
  return <RequestDetail id={use(params).id} />;
}
