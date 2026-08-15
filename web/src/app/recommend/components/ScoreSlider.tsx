export function ScoreSlider({
  label,
  value,
  min,
  max,
  step = 1,
  onChange,
  formatValue,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (value: number) => void;
  formatValue?: (value: number) => string;
}) {
  return (
    <div className="flex items-center gap-4">
      <span className="w-20 shrink-0 text-sm text-neutral-600">{label}</span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="h-1.5 flex-1 cursor-pointer appearance-none rounded-full bg-neutral-200 accent-neutral-900"
      />
      <span className="w-14 shrink-0 text-right text-sm font-semibold text-neutral-900">
        {formatValue ? formatValue(value) : value}
      </span>
    </div>
  );
}
