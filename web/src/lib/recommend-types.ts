// Shared types for the /recommend wizard. Nothing here is persisted or
// sent anywhere — the whole flow is client-side state that ends in a
// search against the real institution API (lib/api.ts), augmented with
// mock program-level data (lib/mock-programs.ts) since no real
// program/admission-requirement data exists yet (see that file's own
// header comment).

export type UndergradRegion = "china_mainland" | "international" | "us";

export type UndergradTier =
  | "shuangfei"
  | "yiben"
  | "211"
  | "985"
  | "c9_elite"
  | "international_other"
  | "us_other";

export type DegreeGoal = "masters" | "phd";

export type FundingNeed = "self_funded" | "prefer_funding" | "need_funding";

export type IntakeTerm = "fall" | "spring" | "either";

export interface AcademicBackground {
  undergradRegion: UndergradRegion | null;
  undergradTier: UndergradTier | null;
  undergradSchoolName: string;
  major: string;
  gpa: number | null;
  gpaScale: 4.0 | 100;
  hasResearchExperience: boolean;
  hasInternshipExperience: boolean;
}

export type TestType = "toefl" | "ielts";

export interface LanguageScores {
  testType: TestType;
  total: number;
  reading: number;
  listening: number;
  speaking: number;
  writing: number;
}

export interface GreScores {
  taken: boolean;
  verbal: number;
  quant: number;
  analyticalWriting: number;
}

export interface TestScores {
  language: LanguageScores;
  gre: GreScores;
}

export interface ApplicationPreferences {
  degreeGoal: DegreeGoal;
  fieldOfStudy: string;
  budgetMinUsd: number;
  budgetMaxUsd: number;
  preferredStates: string[];
  intakeTerm: IntakeTerm;
  fundingNeed: FundingNeed;
}

export interface WizardState {
  background: AcademicBackground;
  scores: TestScores;
  preferences: ApplicationPreferences;
}

export const EMPTY_WIZARD_STATE: WizardState = {
  background: {
    undergradRegion: null,
    undergradTier: null,
    undergradSchoolName: "",
    major: "",
    gpa: null,
    gpaScale: 4.0,
    hasResearchExperience: false,
    hasInternshipExperience: false,
  },
  scores: {
    language: {
      testType: "toefl",
      total: 100,
      reading: 25,
      listening: 25,
      speaking: 25,
      writing: 25,
    },
    gre: {
      taken: false,
      verbal: 155,
      quant: 160,
      analyticalWriting: 3.5,
    },
  },
  preferences: {
    degreeGoal: "masters",
    fieldOfStudy: "",
    budgetMinUsd: 30000,
    budgetMaxUsd: 70000,
    preferredStates: [],
    intakeTerm: "fall",
    fundingNeed: "prefer_funding",
  },
};
