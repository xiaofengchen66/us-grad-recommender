import type { TestScores, TestType } from "@/lib/recommend-types";
import { PillGroup } from "./PillGroup";
import { ScoreSlider } from "./ScoreSlider";

export function TestScoresStep({
  value,
  onChange,
}: {
  value: TestScores;
  onChange: (next: TestScores) => void;
}) {
  const { language, gre } = value;
  const isToefl = language.testType === "toefl";

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-sm font-semibold text-neutral-900">语言考试</h2>
        <div className="mt-3">
          <PillGroup<TestType>
            options={[
              { value: "toefl", label: "TOEFL" },
              { value: "ielts", label: "IELTS" },
            ]}
            value={language.testType}
            onChange={(testType) =>
              onChange({
                ...value,
                language: {
                  ...language,
                  testType,
                  total: testType === "toefl" ? 100 : 7.0,
                  reading: testType === "toefl" ? 25 : 7.0,
                  listening: testType === "toefl" ? 25 : 7.0,
                  speaking: testType === "toefl" ? 25 : 7.0,
                  writing: testType === "toefl" ? 25 : 7.0,
                },
              })
            }
          />
        </div>

        <div className="mt-4 space-y-3">
          <ScoreSlider
            label="总分"
            value={language.total}
            min={isToefl ? 0 : 0}
            max={isToefl ? 120 : 9}
            step={isToefl ? 1 : 0.5}
            onChange={(total) => onChange({ ...value, language: { ...language, total } })}
          />
        </div>

        <div className="mt-4 space-y-3 border-l-2 border-neutral-200 pl-4">
          <p className="text-xs text-neutral-500">单科成绩（部分学校有小分要求）</p>
          <ScoreSlider
            label="阅读"
            value={language.reading}
            min={0}
            max={isToefl ? 30 : 9}
            step={isToefl ? 1 : 0.5}
            onChange={(reading) => onChange({ ...value, language: { ...language, reading } })}
          />
          <ScoreSlider
            label="听力"
            value={language.listening}
            min={0}
            max={isToefl ? 30 : 9}
            step={isToefl ? 1 : 0.5}
            onChange={(listening) => onChange({ ...value, language: { ...language, listening } })}
          />
          <ScoreSlider
            label="口语"
            value={language.speaking}
            min={0}
            max={isToefl ? 30 : 9}
            step={isToefl ? 1 : 0.5}
            onChange={(speaking) => onChange({ ...value, language: { ...language, speaking } })}
          />
          <ScoreSlider
            label="写作"
            value={language.writing}
            min={0}
            max={isToefl ? 30 : 9}
            step={isToefl ? 1 : 0.5}
            onChange={(writing) => onChange({ ...value, language: { ...language, writing } })}
          />
        </div>
      </div>

      <div>
        <h2 className="text-sm font-semibold text-neutral-900">GRE 成绩</h2>
        <div className="mt-3">
          <PillGroup
            options={[
              { value: "no", label: "没有 GRE" },
              { value: "yes", label: "有 GRE 成绩" },
            ]}
            value={gre.taken ? "yes" : "no"}
            onChange={(v) => onChange({ ...value, gre: { ...gre, taken: v === "yes" } })}
          />
        </div>

        {gre.taken && (
          <div className="mt-4 space-y-3 border-l-2 border-neutral-200 pl-4">
            <ScoreSlider
              label="Verbal"
              value={gre.verbal}
              min={130}
              max={170}
              onChange={(verbal) => onChange({ ...value, gre: { ...gre, verbal } })}
            />
            <ScoreSlider
              label="Quant"
              value={gre.quant}
              min={130}
              max={170}
              onChange={(quant) => onChange({ ...value, gre: { ...gre, quant } })}
            />
            <ScoreSlider
              label="写作 (AW)"
              value={gre.analyticalWriting}
              min={0}
              max={6}
              step={0.5}
              onChange={(analyticalWriting) =>
                onChange({ ...value, gre: { ...gre, analyticalWriting } })
              }
            />
          </div>
        )}
      </div>
    </div>
  );
}
