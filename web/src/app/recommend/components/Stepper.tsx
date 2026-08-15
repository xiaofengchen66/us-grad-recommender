const STEP_LABELS = ["学术背景", "标化成绩", "申请偏好", "推荐结果"];

export function Stepper({ currentStep }: { currentStep: number }) {
  return (
    <div className="flex items-center justify-center gap-2">
      {STEP_LABELS.map((label, index) => {
        const stepNumber = index + 1;
        const isActive = stepNumber === currentStep;
        const isDone = stepNumber < currentStep;
        return (
          <div key={label} className="flex items-center gap-2">
            <div className="flex flex-col items-center gap-1">
              <div
                className={`flex h-8 w-8 items-center justify-center rounded-full text-sm font-medium ${
                  isActive
                    ? "bg-neutral-900 text-white"
                    : isDone
                      ? "bg-neutral-900 text-white"
                      : "bg-neutral-200 text-neutral-500"
                }`}
              >
                {stepNumber}
              </div>
              <span
                className={`text-xs whitespace-nowrap ${
                  isActive ? "font-medium text-neutral-900" : "text-neutral-400"
                }`}
              >
                {label}
              </span>
            </div>
            {stepNumber < STEP_LABELS.length && (
              <div
                className={`mb-4 h-px w-6 sm:w-10 ${
                  isDone ? "bg-neutral-900" : "bg-neutral-200"
                }`}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
