import { useEffect, useState } from "react";

const TEXT_STEPS = [
  { label: "Normal", value: 1 },
  { label: "Large", value: 1.25 },
  { label: "Largest", value: 1.55 },
];

/**
 * Persistent accessibility controls. Kept at the top of the page and reachable
 * as the first tab stop after the skip link, because a user who needs larger
 * text needs it before they can read anything else.
 */
const LANGUAGES = [
  { label: "English", value: "en" },
  { label: "ಕನ್ನಡ", value: "kn" },
];

export default function AccessibilityBar({
  readAloud,
  onToggleReadAloud,
  ttsSupported,
  language,
  onChangeLanguage,
}) {
  const [step, setStep] = useState(1);
  const [highContrast, setHighContrast] = useState(false);

  useEffect(() => {
    document.documentElement.style.setProperty("--step", String(step));
  }, [step]);

  useEffect(() => {
    document.documentElement.setAttribute(
      "data-contrast",
      highContrast ? "high" : "normal"
    );
  }, [highContrast]);

  return (
    <div className="a11y-bar" role="group" aria-label="Display, language and reading options">
      <span className="group-label">Language</span>
      {LANGUAGES.map((option) => (
        <button
          key={option.value}
          type="button"
          className="chip"
          lang={option.value}
          aria-pressed={language === option.value}
          onClick={() => onChangeLanguage(option.value)}
        >
          {option.label}
        </button>
      ))}

      <span className="group-label" style={{ marginLeft: "0.75rem" }} id="text-size-label">
        Text size
      </span>
      {TEXT_STEPS.map((option) => (
        <button
          key={option.label}
          type="button"
          className="chip"
          aria-pressed={step === option.value}
          onClick={() => setStep(option.value)}
        >
          {option.label}
        </button>
      ))}

      <span className="group-label" style={{ marginLeft: "0.75rem" }}>
        Display
      </span>
      <button
        type="button"
        className="chip"
        aria-pressed={highContrast}
        onClick={() => setHighContrast((value) => !value)}
      >
        High contrast
      </button>

      {ttsSupported && (
        <>
          <span className="group-label" style={{ marginLeft: "0.75rem" }}>
            Sound
          </span>
          <button
            type="button"
            className="chip"
            aria-pressed={readAloud}
            onClick={onToggleReadAloud}
          >
            Read answers aloud
          </button>
        </>
      )}
    </div>
  );
}
