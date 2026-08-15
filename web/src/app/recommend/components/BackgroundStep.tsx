import type { AcademicBackground, UndergradRegion, UndergradTier } from "@/lib/recommend-types";
import { PillGroup } from "./PillGroup";
import { ScoreSlider } from "./ScoreSlider";

const REGION_OPTIONS: { value: UndergradRegion; label: string }[] = [
  { value: "china_mainland", label: "大陆本科" },
  { value: "international", label: "境外本科（非美国）" },
  { value: "us", label: "美国本科" },
];

const TIER_OPTIONS_MAINLAND: { value: UndergradTier; label: string }[] = [
  { value: "shuangfei", label: "双非" },
  { value: "yiben", label: "普通一本" },
  { value: "211", label: "211" },
  { value: "985", label: "985（除清北和华东五校）" },
  { value: "c9_elite", label: "华东五校 / 清北" },
];

const TIER_OPTIONS_OTHER: { value: UndergradTier; label: string }[] = [
  { value: "international_other", label: "境外院校" },
  { value: "us_other", label: "美国院校" },
];

export function BackgroundStep({
  value,
  onChange,
}: {
  value: AcademicBackground;
  onChange: (next: AcademicBackground) => void;
}) {
  const tierOptions = value.undergradRegion === "china_mainland" ? TIER_OPTIONS_MAINLAND : TIER_OPTIONS_OTHER;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-sm font-semibold text-neutral-900">本科所在地区</h2>
        <p className="mt-1 text-xs text-neutral-500">
          用于粗略参考申请背景，不代表院校排名或录取评估。
        </p>
        <div className="mt-3">
          <PillGroup
            options={REGION_OPTIONS}
            value={value.undergradRegion}
            onChange={(undergradRegion) =>
              onChange({ ...value, undergradRegion, undergradTier: null })
            }
          />
        </div>
      </div>

      {value.undergradRegion && (
        <div>
          <h2 className="text-sm font-semibold text-neutral-900">本科院校层次</h2>
          <p className="mt-1 text-xs text-neutral-500">排名区间仅供大致参考，自行选择即可。</p>
          <div className="mt-3">
            <PillGroup
              options={tierOptions}
              value={value.undergradTier}
              onChange={(undergradTier) => onChange({ ...value, undergradTier })}
            />
          </div>
        </div>
      )}

      <div>
        <label className="text-sm font-semibold text-neutral-900" htmlFor="undergrad-school">
          本科院校名称（选填）
        </label>
        <input
          id="undergrad-school"
          type="text"
          value={value.undergradSchoolName}
          onChange={(e) => onChange({ ...value, undergradSchoolName: e.target.value })}
          placeholder="例如：北京大学"
          className="mt-2 w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-neutral-500 focus:outline-none"
        />
      </div>

      <div>
        <label className="text-sm font-semibold text-neutral-900" htmlFor="major">
          本科专业
        </label>
        <input
          id="major"
          type="text"
          value={value.major}
          onChange={(e) => onChange({ ...value, major: e.target.value })}
          placeholder="例如：计算机科学"
          className="mt-2 w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-neutral-500 focus:outline-none"
        />
      </div>

      <div>
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-neutral-900">GPA</h2>
          <PillGroup
            options={[
              { value: "4.0", label: "4.0 制" },
              { value: "100", label: "百分制" },
            ]}
            value={String(value.gpaScale) as "4.0" | "100"}
            onChange={(scale) => onChange({ ...value, gpaScale: scale === "4.0" ? 4.0 : 100 })}
          />
        </div>
        <div className="mt-3">
          <ScoreSlider
            label="GPA"
            value={value.gpa ?? (value.gpaScale === 4.0 ? 3.5 : 85)}
            min={value.gpaScale === 4.0 ? 2.0 : 60}
            max={value.gpaScale === 4.0 ? 4.0 : 100}
            step={value.gpaScale === 4.0 ? 0.01 : 1}
            onChange={(gpa) => onChange({ ...value, gpa })}
          />
        </div>
      </div>

      <div className="flex flex-wrap gap-6">
        <label className="flex items-center gap-2 text-sm text-neutral-700">
          <input
            type="checkbox"
            checked={value.hasResearchExperience}
            onChange={(e) => onChange({ ...value, hasResearchExperience: e.target.checked })}
            className="h-4 w-4 rounded border-neutral-300"
          />
          有科研经历
        </label>
        <label className="flex items-center gap-2 text-sm text-neutral-700">
          <input
            type="checkbox"
            checked={value.hasInternshipExperience}
            onChange={(e) => onChange({ ...value, hasInternshipExperience: e.target.checked })}
            className="h-4 w-4 rounded border-neutral-300"
          />
          有实习经历
        </label>
      </div>
    </div>
  );
}
