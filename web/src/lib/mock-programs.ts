// ⚠️ MOCK DATA — NOT REAL ADMISSION INFORMATION ⚠️
//
// us_grad_recommender's Program/AdmissionRequirement tables (see
// docs/PHASE_2_CATALOG_DESIGN.md) are structurally built but contain no
// real rows yet — Phase 2.2B built a parser pipeline that can turn a
// fetched catalog page into Program rows, but no live crawling has run
// against any real institution's site. There is currently zero real
// program-level data (degree offered, GRE requirement, cost, deadline,
// acceptance rate) anywhere in this system.
//
// This module exists ONLY so the /recommend wizard's results screen has
// something to render while that real pipeline is built out. Every
// field it produces is a deterministic, clearly-fake placeholder derived
// from the university's real IPEDS data (Carnegie classification,
// enrollment) plus the user's own inputs — it is NOT a real admission
// requirement, cost figure, or deadline for any real program. The UI
// that renders this must never present it without a visible "示例数据"
// (sample data) label. Delete this module once real program ingestion
// (the parser pipeline wired to a live fetch layer) lands and the
// results screen can query real Program/AdmissionRequirement rows
// instead.

import type { UniversitySummary } from "./api";
import type { ApplicationPreferences } from "./recommend-types";

export interface MockProgramCard {
  unitid: number;
  programName: string;
  degreeLabel: string;
  requiresGre: boolean;
  estimatedTotalCostUsdLow: number;
  estimatedTotalCostUsdHigh: number;
  suggestedMinGpa: number;
  referenceAcceptanceRatePercent: number;
  applicationDeadline: string;
  fundingAvailable: boolean;
}

// A small, fixed seed table so the same (university, field) pair always
// renders the same mock numbers within a session — deterministic, not
// random, so it doesn't look like a live API glitching on refresh.
function seededFraction(seedText: string): number {
  let hash = 0;
  for (let i = 0; i < seedText.length; i++) {
    hash = (hash * 31 + seedText.charCodeAt(i)) >>> 0;
  }
  return (hash % 1000) / 1000;
}

const DEGREE_LABELS: Record<ApplicationPreferences["degreeGoal"], string> = {
  masters: "Master of Science",
  phd: "Doctor of Philosophy",
};

export function buildMockProgramCard(
  university: UniversitySummary,
  preferences: ApplicationPreferences,
): MockProgramCard {
  const field = preferences.fieldOfStudy.trim() || "Computer Science";
  const seed = seededFraction(`${university.unitid}:${field}:${preferences.degreeGoal}`);

  const baseCost = university.sector === "public" ? 38000 : 52000;
  const costSpread = 20000 + Math.round(seed * 15000);

  return {
    unitid: university.unitid,
    programName: field,
    degreeLabel: DEGREE_LABELS[preferences.degreeGoal],
    requiresGre: seed > 0.45,
    estimatedTotalCostUsdLow: baseCost,
    estimatedTotalCostUsdHigh: baseCost + costSpread,
    suggestedMinGpa: Math.round((2.8 + seed * 0.9) * 100) / 100,
    referenceAcceptanceRatePercent: Math.round(12 + seed * 55),
    applicationDeadline: seed > 0.5 ? "Dec 15" : "Jan 15",
    fundingAvailable: seed > 0.6,
  };
}
