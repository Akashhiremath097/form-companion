/**
 * Pull identity details out of OCR text from an Indian ID document.
 *
 * OCR on a photographed card is unreliable, so nothing here is treated as
 * certain. Every value comes back with the field it belongs to and is presented
 * to the person for confirmation rather than written straight into the form.
 * Being wrong quietly on someone's bank application is worse than extracting
 * nothing at all.
 */

const MONTHS = {
  jan: "01", feb: "02", mar: "03", apr: "04", may: "05", jun: "06",
  jul: "07", aug: "08", sep: "09", oct: "10", nov: "11", dec: "12",
};

// Lines that are card furniture rather than the holder's details.
const NOISE = [
  "government of india", "unique identification", "aadhaar", "aadhar",
  "भारत सरकार", "आधार", "male", "female", "dob", "date of birth", "year of birth",
  "vid", "issue date", "download", "enrolment", "enrollment", "address",
  "income tax", "permanent account", "govt", "republic of india",
];

function cleanLine(line) {
  return line.replace(/\s+/g, " ").trim();
}

function looksLikeName(line) {
  const lowered = line.toLowerCase();
  if (NOISE.some((n) => lowered.includes(n))) return false;
  if (/\d/.test(line)) return false;
  if (line.length < 4 || line.length > 48) return false;
  // A name is two or more words of letters, allowing initials and hyphens.
  return /^[A-Za-z][A-Za-z\s.'-]+$/.test(line) && line.trim().split(/\s+/).length >= 2;
}

export function parseIdText(rawText) {
  const found = {};
  if (!rawText) return found;

  const text = rawText.replace(/\u00a0/g, " ");
  const lines = text.split("\n").map(cleanLine).filter(Boolean);

  // --- Date of birth ---
  // Numeric first: DOB: 15/03/2004, 15-03-2004
  let match = text.match(/\b(\d{1,2})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{4})\b/);
  if (match) {
    const [, d, m, y] = match;
    found.date_of_birth = `${d.padStart(2, "0")}/${m.padStart(2, "0")}/${y}`;
  } else {
    // Month-name form: 15 Mar 2004
    match = text.match(/\b(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})\b/);
    if (match && MONTHS[match[2].slice(0, 3).toLowerCase()]) {
      found.date_of_birth =
        `${match[1].padStart(2, "0")}/${MONTHS[match[2].slice(0, 3).toLowerCase()]}/${match[3]}`;
    } else {
      // Year of birth only, common on older Aadhaar cards.
      match = text.match(/year\s+of\s+birth\s*:?\s*(\d{4})/i);
      if (match) found.year_of_birth = match[1];
    }
  }

  // --- Gender ---
  if (/\bfemale\b/i.test(text)) found.gender = "Female";
  else if (/\bmale\b/i.test(text)) found.gender = "Male";

  // --- Aadhaar number: 12 digits, usually spaced in groups of four ---
  match = text.match(/\b(\d{4})\s+(\d{4})\s+(\d{4})\b/);
  if (match) found.aadhaar_number = `${match[1]} ${match[2]} ${match[3]}`;

  // --- PAN: five letters, four digits, one letter ---
  match = text.match(/\b([A-Z]{5}\d{4}[A-Z])\b/);
  if (match) found.pan_number = match[1];

  // --- PIN code, taken from an address block ---
  match = text.match(/\b([1-9]\d{5})\b/);
  if (match) found.pin_code = match[1];

  // --- Mobile ---
  match = text.match(/\b([6-9]\d{9})\b/);
  if (match) found.mobile_number = match[1];

  // --- Name ---
  // Prefer the line immediately above the date of birth, which is where the
  // holder's name sits on every Aadhaar layout.
  const dobIndex = lines.findIndex((l) => /dob|date of birth|year of birth/i.test(l));
  if (dobIndex > 0) {
    for (let i = dobIndex - 1; i >= 0 && i >= dobIndex - 3; i -= 1) {
      if (looksLikeName(lines[i])) {
        found.full_name = titleCase(lines[i]);
        break;
      }
    }
  }
  if (!found.full_name) {
    const candidate = lines.find(looksLikeName);
    if (candidate) found.full_name = titleCase(candidate);
  }

  return found;
}

function titleCase(text) {
  return text
    .toLowerCase()
    .split(/\s+/)
    .map((w) => (w.length ? w[0].toUpperCase() + w.slice(1) : w))
    .join(" ");
}

/**
 * Match extracted values to the fields this particular form actually has.
 * Field ids differ between the built-in form and any uploaded PDF, so matching
 * is done on the id and label rather than assuming a fixed schema.
 */
const FIELD_ALIASES = {
  full_name: ["full_name", "name", "applicant_name", "applicant_full_name", "holder_name"],
  date_of_birth: ["date_of_birth", "dob", "birth_date", "dob_ddmmyyyy"],
  gender: ["gender", "sex"],
  mobile_number: ["mobile_number", "mobile", "phone", "mobile_no", "contact_number"],
  pin_code: ["pin_code", "pincode", "pin", "postal_code", "zip"],
  pan_number: ["pan_number", "pan", "pan_no"],
  aadhaar_number: ["aadhaar_number", "aadhaar", "aadhar_number", "national_id", "id_number"],
};

export function matchToFields(extracted, preview) {
  const suggestions = [];
  const taken = new Set();

  // Exact id matches are resolved first. Label matching is a fallback only,
  // because labels overlap in ways ids do not: "Full Name (as per Aadhaar)"
  // contains the word Aadhaar and would otherwise capture the ID number.
  const entries = Object.entries(extracted).filter(([, v]) => v);

  const claim = (key, value, test) => {
    if (taken.has(key)) return false;
    const field = preview.find(
      (f) => !taken.has(f.id) && f.status === "pending" && test(f)
    );
    if (!field) return false;
    taken.add(field.id);
    taken.add(key);
    suggestions.push({ id: field.id, label: field.label, value });
    return true;
  };

  const normLabel = (f) => (f.label || "").toLowerCase().replace(/[^a-z]+/g, "_");

  // Pass 1: the field id is exactly one of the aliases
  for (const [key, value] of entries) {
    const aliases = FIELD_ALIASES[key] || [key];
    claim(key, value, (f) => aliases.includes(f.id.toLowerCase()));
  }

  // Pass 2: the field id contains an alias
  for (const [key, value] of entries) {
    const aliases = FIELD_ALIASES[key] || [key];
    claim(key, value, (f) => aliases.some((a) => f.id.toLowerCase().includes(a)));
  }

  // Pass 3: the label contains an alias
  for (const [key, value] of entries) {
    const aliases = FIELD_ALIASES[key] || [key];
    claim(key, value, (f) => aliases.some((a) => normLabel(f).includes(a)));
  }

  return suggestions;
}
