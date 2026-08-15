import type {
  ApplicationPreferences,
  DegreeGoal,
  FundingNeed,
  IntakeTerm,
} from "@/lib/recommend-types";
import { PillGroup } from "./PillGroup";

const US_STATES = [
  "CA", "TX", "NY", "MA", "IL", "PA", "WA", "GA", "MI", "NC",
  "OH", "VA", "FL", "MD", "CO", "AZ", "MN", "WI", "IN", "TN",
];

export function PreferencesStep({
  value,
  onChange,
}: {
  value: ApplicationPreferences;
  onChange: (next: ApplicationPreferences) => void;
}) {
  function toggleState(state: string) {
    const has = value.preferredStates.includes(state);
    onChange({
      ...value,
      preferredStates: has
        ? value.preferredStates.filter((s) => s !== state)
        : [...value.preferredStates, state],
    });
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-sm font-semibold text-neutral-900">目标学位</h2>
        <div className="mt-3">
          <PillGroup<DegreeGoal>
            options={[
              { value: "masters", label: "硕士 (Master's)" },
              { value: "phd", label: "博士 (PhD)" },
            ]}
            value={value.degreeGoal}
            onChange={(degreeGoal) => onChange({ ...value, degreeGoal })}
          />
        </div>
      </div>

      <div>
        <label className="text-sm font-semibold text-neutral-900" htmlFor="field-of-study">
          意向专业方向
        </label>
        <input
          id="field-of-study"
          type="text"
          value={value.fieldOfStudy}
          onChange={(e) => onChange({ ...value, fieldOfStudy: e.target.value })}
          placeholder="例如：Computer Science, Data Science, Public Policy"
          className="mt-2 w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-neutral-500 focus:outline-none"
        />
      </div>

      <div>
        <h2 className="text-sm font-semibold text-neutral-900">预算范围（每年，美元）</h2>
        <div className="mt-3 flex items-center gap-3">
          <input
            type="number"
            value={value.budgetMinUsd}
            onChange={(e) => onChange({ ...value, budgetMinUsd: Number(e.target.value) })}
            className="w-28 rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-neutral-500 focus:outline-none"
          />
          <span className="text-neutral-400">–</span>
          <input
            type="number"
            value={value.budgetMaxUsd}
            onChange={(e) => onChange({ ...value, budgetMaxUsd: Number(e.target.value) })}
            className="w-28 rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-neutral-500 focus:outline-none"
          />
          <span className="text-xs text-neutral-500">USD / 年</span>
        </div>
      </div>

      <div>
        <h2 className="text-sm font-semibold text-neutral-900">地区偏好（可多选，选填）</h2>
        <div className="mt-3 flex flex-wrap gap-2">
          {US_STATES.map((state) => {
            const isSelected = value.preferredStates.includes(state);
            return (
              <button
                key={state}
                type="button"
                onClick={() => toggleState(state)}
                className={`rounded-full border px-3 py-1.5 text-xs font-medium ${
                  isSelected
                    ? "border-neutral-900 bg-neutral-900 text-white"
                    : "border-neutral-300 bg-white text-neutral-700 hover:border-neutral-400"
                }`}
              >
                {state}
              </button>
            );
          })}
        </div>
      </div>

      <div>
        <h2 className="text-sm font-semibold text-neutral-900">入学季</h2>
        <div className="mt-3">
          <PillGroup<IntakeTerm>
            options={[
              { value: "fall", label: "秋季 (Fall)" },
              { value: "spring", label: "春季 (Spring)" },
              { value: "either", label: "均可" },
            ]}
            value={value.intakeTerm}
            onChange={(intakeTerm) => onChange({ ...value, intakeTerm })}
          />
        </div>
      </div>

      <div>
        <h2 className="text-sm font-semibold text-neutral-900">资金需求</h2>
        <div className="mt-3">
          <PillGroup<FundingNeed>
            options={[
              { value: "self_funded", label: "自费" },
              { value: "prefer_funding", label: "希望有奖助学金" },
              { value: "need_funding", label: "必须有资助才能就读" },
            ]}
            value={value.fundingNeed}
            onChange={(fundingNeed) => onChange({ ...value, fundingNeed })}
          />
        </div>
      </div>
    </div>
  );
}
