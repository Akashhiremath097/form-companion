import { useRef, useState } from "react";

import { matchToFields, parseIdText } from "../lib/idParser";

/**
 * Read an ID document with on-device OCR and offer the details for the form.
 *
 * Two things shape this component. First, the image never leaves the browser:
 * Tesseract runs client-side, so a photograph of someone's Aadhaar card is not
 * uploaded anywhere. Second, nothing is written into the form until the person
 * has seen the values and confirmed them. OCR misreads names and digits often
 * enough that silently filling a bank form from a photo would be reckless.
 */
export default function IdScan({ preview, onConfirm, busy, language }) {
  const inputRef = useRef(null);
  const [status, setStatus] = useState("idle");
  const [progress, setProgress] = useState(0);
  const [suggestions, setSuggestions] = useState([]);
  const [error, setError] = useState(null);

  const runOcr = async (file) => {
    setStatus("working");
    setProgress(0);
    setError(null);
    setSuggestions([]);

    try {
      const { default: Tesseract } = await import("tesseract.js");
      const { data } = await Tesseract.recognize(file, "eng", {
        logger: (m) => {
          if (m.status === "recognizing text") {
            setProgress(Math.round(m.progress * 100));
          }
        },
      });

      const extracted = parseIdText(data.text);
      const matched = matchToFields(extracted, preview);

      if (matched.length === 0) {
        setStatus("empty");
        return;
      }

      setSuggestions(matched);
      setStatus("review");
    } catch (err) {
      setError("That image could not be read. A clearer, straight-on photo usually helps.");
      setStatus("idle");
    }
  };

  const handleChange = (event) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) runOcr(file);
  };

  const toggle = (id) => {
    setSuggestions((current) =>
      current.map((s) => (s.id === id ? { ...s, excluded: !s.excluded } : s))
    );
  };

  const confirm = () => {
    const keep = suggestions.filter((s) => !s.excluded);
    setSuggestions([]);
    setStatus("idle");
    if (keep.length > 0) onConfirm(keep.map(({ id, value }) => ({ field_id: id, value })));
  };

  const dismiss = () => {
    setSuggestions([]);
    setStatus("idle");
  };

  return (
    <div className="scan-bar">
      <div className="scan-copy">
        <strong>Have your ID with you?</strong>
        <span>
          Take a photo of an Aadhaar, PAN or similar card and I will read the details
          off it. The picture stays on your device and is never uploaded.
        </span>
      </div>

      <div className="scan-actions">
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          capture="environment"
          onChange={handleChange}
          disabled={busy || status === "working"}
          className="visually-hidden"
          id="id-scan-input"
        />
        <button
          type="button"
          className="btn secondary"
          onClick={() => inputRef.current?.click()}
          disabled={busy || status === "working"}
        >
          {status === "working" ? `Reading… ${progress}%` : "Scan an ID document"}
        </button>
      </div>

      {error && (
        <p className="scan-message error" role="alert">
          {error}
        </p>
      )}

      {status === "empty" && (
        <p className="scan-message" role="status">
          I could not make out any details from that image. Let us carry on and I will
          ask you directly.
        </p>
      )}

      {status === "review" && (
        <div className="scan-review" role="group" aria-label="Details read from your document">
          <p className="scan-review-head">
            Here is what I read. Untick anything that looks wrong.
          </p>

          <ul className="scan-list">
            {suggestions.map((s) => (
              <li key={s.id}>
                <label className="scan-item">
                  <input
                    type="checkbox"
                    checked={!s.excluded}
                    onChange={() => toggle(s.id)}
                  />
                  <span className="scan-item-label">{s.label}</span>
                  <span className="scan-item-value">{s.value}</span>
                </label>
              </li>
            ))}
          </ul>

          <div className="scan-review-actions">
            <button type="button" className="btn" onClick={confirm} disabled={busy}>
              Use these details
            </button>
            <button type="button" className="btn secondary" onClick={dismiss} disabled={busy}>
              Ignore them
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
