"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { type UniversitySummary, searchUniversities } from "@/lib/api";
import { buildMockProgramCard, type MockProgramCard } from "@/lib/mock-programs";
import type { WizardState } from "@/lib/recommend-types";

interface ResultRow {
  university: UniversitySummary;
  mockProgram: MockProgramCard;
}

export function ResultsStep({ wizard }: { wizard: WizardState }) {
  const [rows, setRows] = useState<ResultRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expandedUnitid, setExpandedUnitid] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function run() {
      setError(null);
      setRows(null);
      try {
        // Real search against the real institution API. Filters derived
        // from the wizard are intentionally limited to what the API
        // actually supports (state, sector, masters_granting) — no
        // program-level filtering exists server-side yet.
        const state = wizard.preferences.preferredStates[0]; // API takes one state at a time
        const res = await searchUniversities({
          state,
          masters_granting: wizard.preferences.degreeGoal === "masters" ? true : undefined,
          limit: 12,
        });
        if (cancelled) return;
        const withMock = res.results.map((university) => ({
          university,
          mockProgram: buildMockProgramCard(university, wizard.preferences),
        }));
        setRows(withMock);
      } catch {
        if (!cancelled) {
          setError(
            "Could not reach the institution API. Is it running at " +
              "NEXT_PUBLIC_API_BASE_URL (default http://localhost:8000)?",
          );
        }
      }
    }

    run();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="space-y-6">
      <div className="rounded-md border border-amber-300 bg-amber-50 px-4 py-3">
        <p className="text-sm font-semibold text-amber-900">⚠️ 示例数据，非真实录取信息</p>
        <p className="mt-1 text-xs text-amber-800">
          下方院校本身是真实 IPEDS 数据（州、性质、Carnegie 分类、在校生规模），但具体项目的费用估算、
          GRE 要求、GPA 门槛、录取率参考、申请截止日期均为演示用的占位数据 —
          真实项目级数据库还在建设中（见 <code className="rounded bg-amber-100 px-1">docs/PHASE_2_CATALOG_DESIGN.md</code>）。
          请勿以此作为实际申请决策依据。
        </p>
      </div>

      {error && (
        <p className="rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>
      )}

      {!error && rows === null && (
        <p className="py-12 text-center text-sm text-neutral-500">正在匹配院校…</p>
      )}

      {rows !== null && rows.length === 0 && !error && (
        <p className="py-12 text-center text-sm text-neutral-500">
          没有匹配的院校，试试放宽地区偏好。
        </p>
      )}

      {rows !== null && rows.length > 0 && (
        <p className="text-sm text-neutral-500">
          为你匹配到 {rows.length} 所真实院校（州/性质/学位层次均为真实筛选条件）
        </p>
      )}

      <div className="space-y-4">
        {rows?.map(({ university, mockProgram }) => {
          const isExpanded = expandedUnitid === university.unitid;
          return (
            <div
              key={university.unitid}
              className="rounded-lg border border-neutral-200 bg-white p-5 shadow-sm"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded bg-neutral-900 px-2 py-0.5 text-xs font-medium text-white">
                      {mockProgram.programName}
                    </span>
                    <span className="text-xs text-neutral-400">示例数据</span>
                    {mockProgram.requiresGre && (
                      <span className="rounded bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
                        需 GRE
                      </span>
                    )}
                  </div>
                  <h3 className="mt-2 text-base font-semibold text-neutral-900">
                    <Link
                      href={`/universities/${university.unitid}`}
                      className="hover:underline"
                    >
                      {university.canonical_name}
                    </Link>
                  </h3>
                  <p className="text-sm text-neutral-500">
                    {[university.city, university.state].filter(Boolean).join(", ")} ·{" "}
                    {university.sector.replace(/_/g, " ")}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-lg font-semibold text-neutral-900">
                    ${mockProgram.estimatedTotalCostUsdLow.toLocaleString()}–$
                    {mockProgram.estimatedTotalCostUsdHigh.toLocaleString()}
                  </p>
                  <p className="text-xs text-neutral-400">预估总花费（示例）/ 年</p>
                </div>
              </div>

              {mockProgram.requiresGre && !wizard.scores.gre.taken && (
                <div className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
                  该项目（示例）要求 GRE，但你尚未提供 GRE 成绩
                </div>
              )}

              <button
                type="button"
                onClick={() =>
                  setExpandedUnitid(isExpanded ? null : university.unitid)
                }
                className="mt-3 text-xs font-medium text-neutral-600 hover:text-neutral-900"
              >
                {isExpanded ? "▲ 收起详情" : "▼ 查看详情"}
              </button>

              {isExpanded && (
                <dl className="mt-3 grid grid-cols-2 gap-3 border-t border-neutral-100 pt-3 text-xs sm:grid-cols-3">
                  <div>
                    <dt className="text-neutral-400">学位</dt>
                    <dd className="font-medium text-neutral-800">{mockProgram.degreeLabel}</dd>
                  </div>
                  <div>
                    <dt className="text-neutral-400">建议 GPA 门槛（示例）</dt>
                    <dd className="font-medium text-neutral-800">
                      {mockProgram.suggestedMinGpa.toFixed(2)} / 4.0
                    </dd>
                  </div>
                  <div>
                    <dt className="text-neutral-400">录取率参考（示例）</dt>
                    <dd className="font-medium text-neutral-800">
                      ~{mockProgram.referenceAcceptanceRatePercent}%
                    </dd>
                  </div>
                  <div>
                    <dt className="text-neutral-400">申请截止日期（示例）</dt>
                    <dd className="font-medium text-neutral-800">{mockProgram.applicationDeadline}</dd>
                  </div>
                  <div>
                    <dt className="text-neutral-400">奖助学金（示例）</dt>
                    <dd className="font-medium text-neutral-800">
                      {mockProgram.fundingAvailable ? "可能提供" : "较少提供"}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-neutral-400">学校性质（真实）</dt>
                    <dd className="font-medium text-neutral-800">
                      {university.sector.replace(/_/g, " ")}
                    </dd>
                  </div>
                </dl>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
