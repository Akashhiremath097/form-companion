import { useRef, useState } from "react";

/**
 * Upload a fillable PDF to use instead of the built-in form.
 *
 * Only PDFs with a real form layer can be read, so the copy says so up front
 * rather than letting someone upload a scan and meet an error afterwards.
 */
export default function FormUpload({ onUpload, busy, disabled }) {
  const inputRef = useRef(null);
  const [fileName, setFileName] = useState(null);

  const handleChange = (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    onUpload(file);
    event.target.value = "";
  };

  return (
    <div className="upload-bar">
      <div className="upload-copy">
        <strong>Using your own form?</strong>
        <span>
          Upload a fillable PDF and I will read its fields, ask you about each one,
          then give you back the completed document.
        </span>
      </div>

      <div className="upload-actions">
        <input
          ref={inputRef}
          id="form-upload"
          type="file"
          accept="application/pdf,.pdf"
          onChange={handleChange}
          disabled={busy || disabled}
          className="visually-hidden"
        />
        <button
          type="button"
          className="btn secondary"
          onClick={() => inputRef.current?.click()}
          disabled={busy || disabled}
        >
          {busy ? "Reading your form…" : "Upload a PDF form"}
        </button>
        {fileName && !busy && <span className="upload-name">{fileName}</span>}
      </div>
    </div>
  );
}
