<div align="center">

# <img src="assets/threepio.webp" alt="" width="48" align="center"> Threepio V1.0

**Role-play your way to better English with Claude, Gemini, or ChatGPT.**

*특정 주제·상황·역할을 설정해 LLM과 음성으로 영어 대화를 연습하고, 세션 종료 시 점수 리포트와 표현 교정을 받는 로컬 웹앱.*

<p>
  <img alt="python" src="https://img.shields.io/badge/python-3.11+-blue?logo=python&logoColor=white">
  <img alt="fastapi" src="https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white">
  <img alt="sqlite" src="https://img.shields.io/badge/SQLite-003B57?logo=sqlite&logoColor=white">
  <img alt="license" src="https://img.shields.io/badge/license-MIT-green">
  <img alt="status" src="https://img.shields.io/badge/status-alpha-orange">
</p>

</div>

---

## Why Threepio?

Most conversation-practice apps are generic. **You** are not — you have a specific paper to defend, a specific interview to prep for, a specific meeting tomorrow. Threepio lets you hand the model your actual materials (your paper, slides, screenshots) and a role (e.g. *"you are a skeptical reviewer at NeurIPS"*), then talks back — out loud — so you can practice the *specific* conversation you're about to have.

Everything runs locally against your own API keys. No accounts, no subscription, no data sent to a third-party SaaS.

## Features

- 🎭 **Custom role-play sessions** — define topic, situation, your role, and the model's role per session
- 📎 **Multi-file attachments** — upload PDFs (your paper, slides) and images (screenshots, figures) directly into the conversation context
- 🤖 **Switch between Claude / Gemini / ChatGPT** per session (you bring your own API key)
- 🎤 **Voice or text** — speak with the browser's Web Speech API, or type. Both work in the same session.
- 🔊 **Spoken replies** — the model's responses are played back via SpeechSynthesis while streaming to the screen
- 📊 **Post-session report** — 100-point scores (quality, fluency, communication, overall) + Korean-language summary + 3–4 suggested phrasing corrections
- 💾 **Session history** — all conversations, attachments, and reports persist in a local SQLite file for later review
- 🏡 **Fully local** — no auth, no server, no telemetry; your materials never leave your machine except via the LLM API you chose

## Demo

> Screenshots / GIF placeholder — PRs welcome.

```
┌─ New Session ─────────────────────────────────┐
│ Title:        My NeurIPS rehearsal            │
│ LLM:          Claude · claude-sonnet-4-6      │
│ Topic:        Explaining my paper             │
│ Situation:    Q&A after a conference talk     │
│ My role:      Paper author                    │
│ Model role:   ML researcher in the audience   │
│ Attachments:  paper.pdf, figure3.png          │
└───────────────────────────────────────────────┘
```

## Quick start

### Prerequisites

- Python 3.11+
- A Chromium-based browser (Chrome, Edge, Brave, Arc) for Web Speech API
- At least one API key: [Anthropic](https://console.anthropic.com/), [Google AI Studio](https://aistudio.google.com/), or [OpenAI](https://platform.openai.com/)

### Install

```bash
git clone https://github.com/<your-username>/threepio.git
cd threepio

# Create an isolated environment (conda shown; venv also fine)
conda create -n threepio python=3.11 -y
conda activate threepio
pip install -r requirements.txt

# Configure API keys — only fill in the ones you want to use
cp .env.example .env
# edit .env

# Run
uvicorn backend.main:app --reload --port 8000
```

Open <http://localhost:8000> in your browser.

### `.env`

```dotenv
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=
OPENAI_API_KEY=sk-...
```

Only providers with a key set are offered in the UI dropdown.

## How it works

```
┌─────────────┐       ┌────────────────────┐       ┌──────────────┐
│  Browser    │ ─SSE─▶│  FastAPI backend   │ ────▶ │ Claude /     │
│  (vanilla   │◀──────│  · session state   │       │ Gemini /     │
│   JS + HTML)│       │  · LLM abstraction │       │ OpenAI API   │
│  STT · TTS  │       │  · SQLite storage  │       └──────────────┘
└─────────────┘       └────────────────────┘
```

- **STT** runs in the browser via the Web Speech API — the browser forwards audio to Google's recognition service and returns text.
- **TTS** runs in the browser via `SpeechSynthesisUtterance` — no cloud calls.
- **LLM calls** go directly from your backend to whichever provider's API you configured, using your key.
- **Streaming**: the backend relays provider deltas over Server-Sent Events, so the UI updates token-by-token and TTS fires on sentence boundaries.
- **Attachments**: PDFs and images are attached to the **first user turn** of the conversation; Claude and Gemini accept them natively, while the OpenAI path extracts PDF text via `pypdf` and embeds it in the system prompt.
- **Post-session scoring** runs the user's utterances back through the same provider with a strict JSON-schema prompt; parsing falls back through several strategies if the model drifts off-format.

## Project layout

```
threepio/
├── backend/
│   ├── main.py         # FastAPI routes, SSE streaming
│   ├── db.py           # SQLite schema + CRUD
│   ├── prompts.py      # Conversation & feedback prompt templates
│   ├── scoring.py      # Post-session JSON feedback generator
│   ├── schemas.py      # Pydantic request models
│   └── llm/
│       ├── base.py     # LLMClient abstract interface
│       ├── claude.py   # Anthropic implementation
│       ├── gemini.py   # google-genai implementation
│       └── openai_impl.py  # OpenAI implementation (+ PDF text fallback)
├── frontend/
│   ├── index.html      # Home · New · Chat · Detail views
│   ├── style.css
│   └── app.js          # Router, STT/TTS, SSE consumer
└── data/
    ├── app.db          # SQLite (created at runtime)
    └── uploads/        # Attachment files, grouped by session id
```

## API reference

All endpoints live under `/api`. The backend also serves the static frontend from `/`.

| Method | Path | Description |
|--------|------|-------------|
| GET    | `/api/providers` | List providers + availability (keyed by which API keys are set) |
| POST   | `/api/sessions` | Create session |
| POST   | `/api/sessions/{id}/attachments` | Upload one or more files (multipart) |
| POST   | `/api/sessions/{id}/start` | Begin the conversation; SSE stream of the model's opening turn |
| POST   | `/api/sessions/{id}/messages` | Send a user turn; SSE stream of the model's reply |
| POST   | `/api/sessions/{id}/end` | End session and generate scoring/feedback |
| GET    | `/api/sessions` | List sessions |
| GET    | `/api/sessions/{id}` | Full session detail (messages, attachments, feedback) |

Interactive docs are available at `/docs` when the server is running.

## Costs

Threepio is **not** a hosted service — there is nothing to pay the authors. API usage bills directly to your own account with the provider you chose. Typical per-session cost (a few short turns + a scoring call) is on the order of cents, but it depends on model choice and context size (attached PDFs are the biggest variable).

## Limitations (v1)

- **Browser support**: Web Speech API works best in Chromium. Firefox and Safari are limited or unsupported for STT.
- **OpenAI PDFs**: Chat Completions can't take PDFs directly, so we extract text with `pypdf`. Complex layouts (multi-column, figures, LaTeX) won't transfer as cleanly as on Claude/Gemini, which receive the file natively.
- **Fluency score is approximated from text** (sentence completeness, filler-word frequency, self-corrections). True audio-timing fluency measurement is out of scope here.
- **Single-user, local-only** by design — no authentication, no multi-user session isolation.
- Korean-language output in the feedback report is hardcoded in the prompt; generalize if you need other L1s.

## Roadmap ideas

Contributions welcome for any of these:

- [ ] Whisper-based server-side STT (for Firefox/Safari support and privacy)
- [ ] Higher-quality TTS (ElevenLabs / OpenAI TTS / Google Cloud TTS)
- [ ] OpenAI Assistants/Responses API path so OpenAI can also consume PDFs natively
- [ ] Session tags, search, and export (Markdown / PDF)
- [ ] Docker / docker-compose for one-command setup
- [ ] Internationalized feedback-language selector
- [ ] Per-turn audio timing capture for real fluency scoring

## Contributing

Issues and PRs are welcome. For non-trivial changes, please open an issue first to discuss the direction.

Rough workflow:
1. Fork, create a branch
2. `conda env create` or `pip install -r requirements.txt` in a venv
3. `uvicorn backend.main:app --reload` to develop
4. If you touch the LLM abstraction, make sure the change works for all three providers (or gate it behind the provider that supports it)
5. Open a PR describing the change and the manual test you ran

## Privacy

- All session data (messages, attachments, reports) is stored in `data/app.db` and `data/uploads/` on your machine.
- Attachments are sent to the LLM provider you selected for that session — that's the only network egress of your files.
- The browser's Web Speech API transmits microphone audio to Google's recognition service. If that is unacceptable for your threat model, use text input only (the mic button can be ignored entirely) or implement the Whisper-STT roadmap item.

## Acknowledgments

Built with [FastAPI](https://fastapi.tiangolo.com/), the [Anthropic](https://github.com/anthropics/anthropic-sdk-python), [google-genai](https://github.com/googleapis/python-genai), and [OpenAI](https://github.com/openai/openai-python) SDKs, [pypdf](https://github.com/py-pdf/pypdf), and the browser's native Web Speech / SpeechSynthesis APIs.

## License
no commercial use, only for education
MIT — see [LICENSE](LICENSE).
