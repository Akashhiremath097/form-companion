const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

async function request(path, options = {}) {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!response.ok) {
    let detail = "Something went wrong. Please try again.";
    try {
      const body = await response.json();
      if (body.detail) detail = body.detail;
    } catch {
      /* keep the default message */
    }
    throw new Error(detail);
  }

  return response.json();
}

export const api = {
  startSession: (language = "en") =>
    request("/api/sessions", {
      method: "POST",
      body: JSON.stringify({ language }),
    }),

  uploadForm: async (file, language = "en") => {
    const body = new FormData();
    body.append("file", file);

    const response = await fetch(`${BASE_URL}/api/forms/upload?language=${language}`, {
      method: "POST",
      body,
    });

    if (!response.ok) {
      let detail = "That form could not be read.";
      try {
        const parsed = await response.json();
        if (parsed.detail) detail = parsed.detail;
      } catch {
        /* keep the default */
      }
      throw new Error(detail);
    }

    return response.json();
  },

  downloadUrl: (sessionId) => `${BASE_URL}/api/sessions/${sessionId}/download`,

  setLanguage: (sessionId, language) =>
    request(`/api/sessions/${sessionId}/language`, {
      method: "POST",
      body: JSON.stringify({ language }),
    }),

  sendAnswer: (sessionId, reply) =>
    request(`/api/sessions/${sessionId}/answer`, {
      method: "POST",
      body: JSON.stringify({ reply }),
    }),

  simplify: (sessionId) =>
    request(`/api/sessions/${sessionId}/simplify`, { method: "POST" }),

  getPreview: (sessionId) => request(`/api/sessions/${sessionId}/preview`),

  resetField: (sessionId, fieldId) =>
    request(`/api/sessions/${sessionId}/reset-field`, {
      method: "POST",
      body: JSON.stringify({ field_id: fieldId }),
    }),
};
