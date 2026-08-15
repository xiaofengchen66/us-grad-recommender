"use client";

import { useState } from "react";
import Link from "next/link";
import { BackgroundStep } from "./components/BackgroundStep";
import { PreferencesStep } from "./components/PreferencesStep";
import { ResultsStep } from "./components/ResultsStep";
import { Stepper } from "./components/Stepper";
import { TestScoresStep } from "./components/TestScoresStep";
import { EMPTY_WIZARD_STATE, type WizardState } from "@/lib/recommend-types";

const TOTAL_STEPS = 4;

export default function RecommendPage() {
  const [step, setStep] = useState(1);
  const [wizard, setWizard] = useState<WizardState>(EMPTY_WIZARD_STATE);

  function goNext() {
    setStep((s) => Math.min(s + 1, TOTAL_STEPS));
  }
  function goBack() {
    setStep((s) => Math.max(s - 1, 1));
  }

  return (
    <div className="min-h-screen bg-neutral-50 text-neutral-900">
      <main className="mx-auto max-w-2xl px-6 py-12">
        <Link href="/" className="text-xs text-neutral-500 hover:text-neutral-800">
          ← 返回院校搜索
        </Link>
        <h1 className="mt-3 text-2xl font-semibold tracking-tight">选校助手</h1>
        <p className="mt-2 text-sm text-neutral-600">
          告诉我们你的背景和标化成绩，为你匹配真实院校 — 项目级录取要求/费用目前为示例数据，
          详见结果页说明。
        </p>

        <div className="mt-8">
          <Stepper currentStep={step} />
        </div>

        <div className="mt-8 rounded-lg border border-neutral-200 bg-white p-6 shadow-sm">
          {step === 1 && (
            <BackgroundStep
              value={wizard.background}
              onChange={(background) => setWizard({ ...wizard, background })}
            />
          )}
          {step === 2 && (
            <TestScoresStep
              value={wizard.scores}
              onChange={(scores) => setWizard({ ...wizard, scores })}
            />
          )}
          {step === 3 && (
            <PreferencesStep
              value={wizard.preferences}
              onChange={(preferences) => setWizard({ ...wizard, preferences })}
            />
          )}
          {step === 4 && <ResultsStep wizard={wizard} />}
        </div>

        <div className="mt-6 flex items-center justify-between">
          <button
            type="button"
            onClick={goBack}
            disabled={step === 1}
            className="rounded-md border border-neutral-300 bg-white px-5 py-2.5 text-sm font-medium text-neutral-700 shadow-sm hover:bg-neutral-50 disabled:cursor-not-allowed disabled:opacity-40"
          >
            上一步
          </button>
          {step < TOTAL_STEPS ? (
            <button
              type="button"
              onClick={goNext}
              className="rounded-md bg-neutral-900 px-5 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-neutral-700"
            >
              下一步
            </button>
          ) : (
            <button
              type="button"
              onClick={() => {
                setWizard(EMPTY_WIZARD_STATE);
                setStep(1);
              }}
              className="rounded-md border border-neutral-300 bg-white px-5 py-2.5 text-sm font-medium text-neutral-700 shadow-sm hover:bg-neutral-50"
            >
              重新开始
            </button>
          )}
        </div>
      </main>
    </div>
  );
}
