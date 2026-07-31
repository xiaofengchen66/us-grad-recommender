"use client";

import Link from "next/link";
import { useState, useTransition } from "react";
import {
  type Sector,
  type UniversitySummary,
  searchUniversities,
} from "@/lib/api";

const SECTORS: { value: Sector | ""; label: string }[] = [
  { value: "", label: "Any sector" },
  { value: "public", label: "Public" },
  { value: "private_nonprofit", label: "Private nonprofit" },
  { value: "private_for_profit", label: "Private for-profit" },
];

export default function Home() {
  const [q, setQ] = useState("");
  const [state, setState] = useState("");
  const [sector, setSector] = useState<Sector | "">("");
  const [mastersOnly, setMastersOnly] = useState(true);
  const [results, setResults] = useState<UniversitySummary[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function runSearch(e?: React.FormEvent) {
    e?.preventDefault();
    setError(null);
    startTransition(async () => {
      try {
        const res = await searchUniversities({
          q: q || undefined,
          state: state || undefined,
          sector: sector || undefined,
          masters_granting: mastersOnly ? true : undefined,
          limit: 25,
        });
        setResults(res.results);
        setTotal(res.total);
      } catch {
        setError(
          "Could not reach the institution API. Is it running at " +
            "NEXT_PUBLIC_API_BASE_URL (default http://localhost:8000)?",
        );
        setResults(null);
      }
    });
  }

  return (
    <div className="min-h-screen bg-neutral-50 text-neutral-900">
      <main className="mx-auto max-w-3xl px-6 py-12">
        <h1 className="text-2xl font-semibold tracking-tight">
          US Graduate Recommender
        </h1>
        <p className="mt-2 text-sm text-neutral-600">
          Institution search — real IPEDS 2023 data, read-only. Program,
          funding, and outcome data don&apos;t exist yet — see{" "}
          <code className="rounded bg-neutral-200 px-1 py-0.5 text-xs">
            docs/FULL_HANDOFF.md
          </code>{" "}
          for the roadmap.
        </p>

        <form onSubmit={runSearch} className="mt-8 space-y-3">
          <input
            type="text"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search by institution name or alias (e.g. LSU, Louisiana State)"
            className="w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-neutral-500 focus:outline-none"
          />
          <div className="flex flex-wrap items-center gap-3">
            <input
              type="text"
              value={state}
              onChange={(e) => setState(e.target.value.toUpperCase().slice(0, 2))}
              placeholder="State (e.g. LA)"
              maxLength={2}
              className="w-28 rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-neutral-500 focus:outline-none"
            />
            <select
              value={sector}
              onChange={(e) => setSector(e.target.value as Sector | "")}
              className="rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-neutral-500 focus:outline-none"
            >
              {SECTORS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
            <label className="flex items-center gap-2 text-sm text-neutral-700">
              <input
                type="checkbox"
                checked={mastersOnly}
                onChange={(e) => setMastersOnly(e.target.checked)}
                className="h-4 w-4 rounded border-neutral-300"
              />
              Master&apos;s-granting only
            </label>
            <button
              type="submit"
              disabled={isPending}
              className="ml-auto rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-neutral-700 disabled:opacity-50"
            >
              {isPending ? "Searching…" : "Search"}
            </button>
          </div>
        </form>

        {error && (
          <p className="mt-6 rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </p>
        )}

        {results !== null && !error && (
          <div className="mt-8">
            <p className="text-sm text-neutral-500">
              {total} result{total === 1 ? "" : "s"}
              {total > results.length ? ` (showing first ${results.length})` : ""}
            </p>
            <ul className="mt-3 divide-y divide-neutral-200 rounded-md border border-neutral-200 bg-white">
              {results.map((u) => (
                <li key={u.unitid}>
                  <Link
                    href={`/universities/${u.unitid}`}
                    className="flex items-center justify-between gap-4 px-4 py-3 text-sm hover:bg-neutral-50"
                  >
                    <span>
                      <span className="font-medium text-neutral-900">
                        {u.canonical_name}
                      </span>
                      <span className="ml-2 text-neutral-500">
                        {[u.city, u.state].filter(Boolean).join(", ")}
                      </span>
                    </span>
                    <span className="shrink-0 text-xs uppercase tracking-wide text-neutral-400">
                      {u.sector.replace(/_/g, " ")}
                    </span>
                  </Link>
                </li>
              ))}
              {results.length === 0 && (
                <li className="px-4 py-6 text-center text-sm text-neutral-500">
                  No matches.
                </li>
              )}
            </ul>
          </div>
        )}
      </main>
    </div>
  );
}
