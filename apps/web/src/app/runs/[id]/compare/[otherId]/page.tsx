"use client";

import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";

export default function LegacyComparePage() {
  const { id, otherId } = useParams<{ id: string; otherId: string }>();
  const router = useRouter();

  useEffect(() => {
    router.replace(`/compare?a=${id}&b=${otherId}`);
  }, [id, otherId, router]);

  return <p className="text-neutral-500">Redirecting…</p>;
}
