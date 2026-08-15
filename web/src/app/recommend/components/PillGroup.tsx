interface PillOption<T extends string> {
  value: T;
  label: string;
}

export function PillGroup<T extends string>({
  options,
  value,
  onChange,
  columns = "auto",
}: {
  options: PillOption<T>[];
  value: T | null;
  onChange: (value: T) => void;
  columns?: "auto" | 2 | 3;
}) {
  // Tailwind needs statically-analyzable class names (no runtime string
  // interpolation), hence the lookup table instead of a template string.
  const gridClass =
    columns === 2
      ? "grid grid-cols-2 gap-2"
      : columns === 3
        ? "grid grid-cols-3 gap-2"
        : "flex flex-wrap gap-2";
  return (
    <div className={gridClass}>
      {options.map((option) => {
        const isSelected = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            className={`rounded-full border px-4 py-2 text-sm font-medium transition-colors ${
              isSelected
                ? "border-neutral-900 bg-neutral-900 text-white"
                : "border-neutral-300 bg-white text-neutral-700 hover:border-neutral-400"
            }`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
