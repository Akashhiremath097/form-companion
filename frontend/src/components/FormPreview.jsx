const STATUS_TEXT = {
  filled: "Filled",
  skipped: "Left blank",
  pending: "Awaiting",
};

/**
 * Live view of the form as an official document.
 *
 * Real bank forms group fields into lettered sections, so the preview does the
 * same: seeing the document take shape is more reassuring than watching a list
 * of statuses, particularly for someone who has been handed this form at a
 * counter and told to fill it in.
 *
 * Status is conveyed by text and border treatment as well as colour, so the
 * panel still reads correctly for colour-blind users and in high-contrast mode.
 */

const SECTIONS = [
  {
    letter: "A",
    title: "Personal Details",
    fields: ["full_name", "date_of_birth", "occupation"],
  },
  {
    letter: "B",
    title: "Contact Details",
    fields: ["mobile_number", "email", "address_line", "city", "pincode"],
  },
  {
    letter: "C",
    title: "Account Details",
    fields: ["account_type", "nominee_name"],
  },
];

export default function FormPreview({
  formTitle,
  preview,
  progress,
  currentFieldId,
  onEdit,
  complete,
}) {
  const total = progress?.total || 1;
  const resolved = (progress?.answered || 0) + (progress?.skipped || 0);
  const percent = Math.round((resolved / total) * 100);

  const byId = Object.fromEntries(preview.map((field) => [field.id, field]));

  // Anything the schema adds later that is not listed above still gets shown,
  // so a new field never silently disappears from the preview.
  const known = new Set(SECTIONS.flatMap((section) => section.fields));
  const extras = preview.filter((field) => !known.has(field.id));

  const renderField = (field, index) => {
    if (!field) return null;
    const isCurrent = field.id === currentFieldId;

    return (
      <div
        key={field.id}
        className={`doc-field ${field.status} ${isCurrent ? "current" : ""}`}
        aria-current={isCurrent ? "step" : undefined}
      >
        <div className="doc-field-head">
          <span className="doc-field-number">{index}.</span>
          <span className="doc-field-label">
            {field.label}
            {field.required && <abbr title="Required"> *</abbr>}
          </span>
          {field.status !== "pending" && (
            <button type="button" className="doc-edit" onClick={() => onEdit(field.id)}>
              Change
              <span className="visually-hidden"> {field.label}</span>
            </button>
          )}
        </div>

        <div className="doc-field-box">
          {field.value ? (
            <span className="doc-value">{field.value}</span>
          ) : (
            <span className="doc-value empty">
              {field.status === "skipped" ? "\u2014 left blank \u2014" : ""}
            </span>
          )}
          <span className={`doc-stamp ${field.status}`}>{STATUS_TEXT[field.status]}</span>
        </div>
      </div>
    );
  };

  let counter = 0;

  return (
    <section className="panel document" aria-labelledby="form-heading">
      <header className="doc-masthead">
        <div>
          <p className="doc-eyebrow">Application form</p>
          <h2 id="form-heading">{formTitle || "Your form"}</h2>
        </div>
        <span className="doc-progress">
          {resolved} of {total}
        </span>
      </header>

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

      <div className="doc-body">
        {SECTIONS.map((section) => {
          const fields = section.fields.map((id) => byId[id]).filter(Boolean);
          if (fields.length === 0) return null;

          return (
            <section key={section.letter} className="doc-section">
              <h3 className="doc-section-head">
                <span className="doc-section-letter">{section.letter}</span>
                {section.title}
              </h3>
              {fields.map((field) => {
                counter += 1;
                return renderField(field, counter);
              })}
            </section>
          );
        })}

        {extras.length > 0 && (
          <section className="doc-section">
            <h3 className="doc-section-head">
              <span className="doc-section-letter">D</span>
              Other Details
            </h3>
            {extras.map((field) => {
              counter += 1;
              return renderField(field, counter);
            })}
          </section>
        )}
      </div>

      <footer className="doc-footer">
        <span>* Required field</span>
        {complete && (
          <span className="doc-complete" role="status">
            Ready for review
          </span>
        )}
      </footer>
    </section>
  );
}
