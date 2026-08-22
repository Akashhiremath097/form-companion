---
title: Form Companion
emoji: 📝
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# Form Companion

Conversational form filling for people who face visual, cognitive, or literacy barriers.

**CodeFury 9.0 — Theme 2: Accessibility & Inclusive Technology**

---

## The problem

Official forms assume a lot: that you can read small print, parse terms like *nominee* and *zero balance*, track which of thirty boxes you have already filled, and get it all right the first time. For someone with low vision, low literacy, or a cognitive disability, a bank account form is not paperwork — it is a wall.

## What this does

Form Companion turns a form into a conversation. It asks one thing at a time, in plain language, and accepts answers however the person naturally gives them — typed or spoken, "5th March 2001" or "05/03/2001". The form fills in beside the conversation so progress is always visible, and any question can be explained in simpler words on request.

## Features

- **One question at a time** — no wall of fields, no scrolling back to check what you missed
- **Answer in your own words** — an LLM extracts and normalises the value from natural phrasing
- **Answer by voice** — speech-to-text via the Web Speech API, no extra hardware
- **Read aloud** — every assistant message can be spoken back
- **"Explain this question"** — plain-language explanation of any field, on demand
- **Live form preview** — see fields fill in as you go, with clear filled / left blank / not yet status
- **Change any answer** — click *Change* on any completed field to redo it
- **Text size and high contrast controls** — three text sizes, WCAG-compliant contrast toggle

## Accessibility

Built to WCAG 2.1 AA:

- Typeface is **Atkinson Hyperlegible**, designed by the Braille Institute for low-vision readers
- All contrast ratios meet or exceed 4.5:1; a high-contrast mode pushes further
- Field status is conveyed by text and border style, never by colour alone
- Full keyboard navigation with a visible focus ring and a skip link
- Conversation is an ARIA live region so screen readers announce new messages
- Text scales to 155% without layout breaking
- `prefers-reduced-motion` respected

## Architecture

```
React + Vite  ──REST──>  FastAPI  ──>  Groq LLaMA 3.3 70B
   (Vercel)                (Render)
```

Three backend layers, deliberately separated:

| Layer | Responsibility |
|---|---|
| `llm_service.py` | Asks questions, extracts values, simplifies explanations |
| `validation.py` | Decides whether an extracted value is actually acceptable |
| `session_store.py` | Tracks answers and serves the next unfilled field |

The LLM shapes the answer; deterministic validation gates it. That split means a bad LLM response cannot put garbage into the form, and every LLM call has a non-LLM fallback path, so the app stays usable if Groq times out.

## Running locally

**Backend**

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env          # add your GROQ_API_KEY
python -m uvicorn main:app --reload --port 8000
```

**Frontend**

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Open http://localhost:5173

**Tests**

```bash
cd backend && python -m pytest -q     # 24 tests, no API key needed
```

## Deploying

- **Backend → Render**: `render.yaml` is included. Set `GROQ_API_KEY` and `ALLOWED_ORIGINS` (your Vercel URL) as environment variables.
- **Frontend → Vercel**: import the repo, set root directory to `frontend`, and set `VITE_API_URL` to your Render URL.
- GitHub Actions runs backend tests and a frontend build on every push.

## Privacy

Form answers may contain personal and financial information, so:

- Answers live in server memory for the session only and are never written to disk
- Field values are never logged — only field IDs and status
- No account required, no tracking, nothing persists after the session ends

## Adding another form

Drop a new JSON file in `backend/data/` following the same schema as `bank_form_schema.json`. Every field needs `id`, `label`, `type`, `help_text`, and a `question_hint` telling the LLM how to ask for it. No other code changes are required.

## Prompts implemented

Three system prompts drive the assistant, all in `services/llm_service.py`:

1. **`ASK_SYSTEM`** — generates the conversational question for each field. Constrains the model to one question, everyday words, under 40 words, plain text only.
2. **`EXTRACT_SYSTEM`** — pulls a clean value out of a natural reply and returns strict JSON with `value`, `skipped`, `needs_clarification`, and `clarification`. Includes per-type cleaning rules (phone numbers, dates, PIN codes, fixed-choice mapping).
3. **`SIMPLIFY_SYSTEM`** — explains a field at a reading level a 12-year-old would follow, covering what it is, why it is asked, and where to find the answer.

## Team

Akash Hiremath — github.com/Akashhiremath097
