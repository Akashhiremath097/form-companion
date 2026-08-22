const STATUS_TEXT = {
  filled: "Filled",
  skipped: "Left blank",
  pending: "Not yet",
};

/**
 * Live view of the form as it fills in.
 *
 * Status is conveyed by text and border style as well as colour, so the panel
 * still reads correctly for colour-blind users and in high-contrast mode.
 */
export default function FormPreview({ formTitle, preview, progress, currentFieldId, onEdit, complete }) {
  const total = progress?.total || 1;
  const resolved = (progress?.answered || 0) + (progress?.skipped || 0);
  const percent = Math.round((resolved / total) * 100);

  return (
    <section className="panel" aria-labelledby="form-heading">
      <div className="panel-head">
        <h2 id="form-heading">{formTitle || "Your form"}</h2>
        <span className="progress-note">
          {resolved} of {total} done
        </span>
      </div>

      <div
        className="progress-rail"
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Form completion"
      >
        <div className="progress-fill" style={{ width: `${percent}%` }} />
      </div>

      <ul className="field-list">
        {preview.map((field) => {
          const isCurrent = field.id === currentFieldId;
          return (
            <li
              key={field.id}
              className={`field-row ${isCurrent ? "current" : ""}`}
              aria-current={isCurrent ? "step" : undefined}
            >
              <span className={`field-status ${field.status}`}>
                {STATUS_TEXT[field.status]}
              </span>

              <div className="field-body">
                <span className="field-label">
                  {field.label}
                  {!field.required && " (optional)"}
                </span>
                {field.value ? (
                  <span className="field-value">{field.value}</span>
                ) : (
                  <span className="field-value empty">
                    {field.status === "skipped" ? "Left blank" : "Waiting for your answer"}
                  </span>
                )}
              </div>

              {field.status !== "pending" && (
                <button
                  type="button"
                  className="field-edit"
                  onClick={() => onEdit(field.id)}
                >
                  Change
                  <span className="visually-hidden"> {field.label}</span>
                </button>
              )}
            </li>
          );
        })}
      </ul>

      {complete && (
        <p className="done-banner" role="status">
          Your form is complete. Review it above and change anything that looks wrong.
        </p>
      )}
    </section>
  );
}
