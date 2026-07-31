import Link from "next/link";
import { notFound } from "next/navigation";
import { getUniversity } from "@/lib/api";

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div className="border-b border-neutral-100 py-2 last:border-0">
      <dt className="text-xs uppercase tracking-wide text-neutral-400">
        {label}
      </dt>
      <dd className="mt-0.5 text-sm text-neutral-900">{value}</dd>
    </div>
  );
}

export default async function UniversityPage({
  params,
}: {
  params: Promise<{ unitid: string }>;
}) {
  const { unitid } = await params;
  const id = Number(unitid);
  if (!Number.isInteger(id)) notFound();

  const u = await getUniversity(id);
  if (!u) notFound();

  return (
    <div className="min-h-screen bg-neutral-50 text-neutral-900">
      <main className="mx-auto max-w-2xl px-6 py-12">
        <Link
          href="/"
          className="text-sm text-neutral-500 hover:text-neutral-800"
        >
          ← Back to search
        </Link>

        <h1 className="mt-3 text-2xl font-semibold tracking-tight">
          {u.canonical_name}
        </h1>
        <p className="mt-1 text-sm text-neutral-600">
          {[u.city, u.state].filter(Boolean).join(", ")}
          {u.website && (
            <>
              {" · "}
              <a
                href={
                  u.website.startsWith("http") ? u.website : `https://${u.website}`
                }
                target="_blank"
                rel="noopener noreferrer"
                className="underline hover:text-neutral-900"
              >
                {u.website}
              </a>
            </>
          )}
        </p>

        <dl className="mt-8 rounded-md border border-neutral-200 bg-white px-4">
          <Field label="Sector" value={u.sector.replace(/_/g, " ")} />
          <Field label="Highest degree offered" value={u.highest_degree_label} />
          <Field
            label="Carnegie classification"
            value={u.carnegie_classification_label}
          />
          <Field label="Campus setting" value={u.campus_setting_label} />
          <Field
            label="Total enrollment"
            value={
              u.total_enrollment
                ? `${u.total_enrollment.toLocaleString()} (${u.enrollment_year})`
                : null
            }
          />
          <Field
            label="Graduate enrollment"
            value={u.graduate_enrollment?.toLocaleString()}
          />
          <Field
            label="International graduate enrollment"
            value={u.international_graduate_enrollment?.toLocaleString()}
          />
          <Field
            label="Aliases"
            value={
              u.aliases.length > 0
                ? u.aliases.map((a) => a.alias).join(" · ")
                : null
            }
          />
        </dl>

        <div className="mt-6 rounded-md bg-amber-50 px-4 py-3 text-xs text-amber-800">
          <p className="font-medium">Master&apos;s-granting: {u.masters_granting ? "yes" : "no"}</p>
          {u.masters_granting_basis && <p className="mt-1">{u.masters_granting_basis}</p>}
        </div>

        <p className="mt-4 text-xs text-neutral-400">
          Source: {u.source_dataset} · Last verified {u.last_verified_at} · No
          program, funding, or outcome data exists for this institution yet
          (Phase 1 institution index only).
        </p>
      </main>
    </div>
  );
}
