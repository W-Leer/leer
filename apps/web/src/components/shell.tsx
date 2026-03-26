"use client";

import { Sidebar } from "./sidebar";

export function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto px-8 py-8">
        {children}
      </main>
    </div>
  );
}
