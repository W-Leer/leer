"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export function Sidebar() {
  const pathname = usePathname();
  const isRuns = pathname === "/" || pathname.startsWith("/runs");
  const isCompare = pathname.includes("/compare");

  return (
    <aside className="flex h-screen w-52 shrink-0 flex-col border-r border-neutral-100 bg-white">
      {/* Logo */}
      <div className="flex items-center gap-2 border-b border-neutral-100 px-5 py-4">
        <Link href="/" className="text-lg font-semibold tracking-tight text-neutral-900">
          Leer
        </Link>
        <span className="rounded bg-neutral-100 px-1.5 py-0.5 text-[10px] font-medium text-neutral-400">
          dev
        </span>
      </div>

      {/* Project */}
      <div className="border-b border-neutral-100 px-5 py-3">
        <div className="text-[10px] font-medium uppercase tracking-wider text-neutral-400">
          Project
        </div>
        <div className="mt-0.5 text-sm font-medium text-neutral-700">demo-project</div>
      </div>

      {/* Navigation */}
      <nav className="flex flex-col gap-0.5 px-3 py-3">
        <NavLink href="/" label="Runs" active={isRuns && !isCompare} />
        <NavLink href="/" label="Compare" active={isCompare} />
      </nav>
    </aside>
  );
}

function NavLink({
  href,
  label,
  active,
}: {
  href: string;
  label: string;
  active: boolean;
}) {
  return (
    <Link
      href={href}
      className={`block rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
        active
          ? "bg-neutral-100 text-neutral-900"
          : "text-neutral-500 hover:bg-neutral-50 hover:text-neutral-700"
      }`}
    >
      {label}
    </Link>
  );
}
