# Threepio — 개인화 영어 회화 웹앱

## Context
사용자는 특정 주제·상황·역할을 지정해 선택한 LLM(Claude / Gemini / ChatGPT)과 **음성 또는 텍스트**로 영어 회화를 연습하고 싶어함. 예: 내 논문 PDF 여러 개를 첨부 → 역할 "논문 저자 vs ML 연구자", 상황 "학회 Q&A" → 모델이 먼저 질문하고 내가 답하는 대화 진행. 세션 종료 시 **① 어색한 표현 3~4개 교정 + ② 100점 만점의 점수(질·유창성·의미전달) 리포트**를 제공, 모든 세션은 저장·재열람 가능.

현재 작업 디렉토리(`/Users/yujinbae/Desktop/code`)는 비어있는 [threepio/](threepio/) 폴더를 포함한 greenfield 상태.

## 기술 스택 (결정됨)
| 영역 | 선택 | 사유 |
|------|------|------|
| 실행 환경 | **conda env `threepio` (Python 3.11)** | 사용자 요청, 의존성 격리 |
| 백엔드 | FastAPI + uvicorn | async/SSE 스트리밍, OpenAPI 문서 자동 |
| DB | SQLite (`sqlite3` 표준) | 설치 불필요, 관계형 관리 |
| LLM | **Claude / Gemini / ChatGPT 3종 전환 가능** | 세션 생성 시 선택, 각 프로바이더 API 사용 |
| STT | 브라우저 Web Speech API | 무료, Chrome 영어 인식 정확 |
| TTS | 브라우저 SpeechSynthesis API | 설치 불필요, 학습용 충분 |
| 텍스트 입력 | 항상 노출된 입력 박스 | 음성 실패/불가 환경 fallback |
| 첨부 | **PDF + 이미지 복수 업로드** | Claude/Gemini native, OpenAI는 PDF→텍스트 추출 |
| 프론트 | Vanilla HTML/CSS/JS | 빌드 없음, 단일 명령 실행 |

### LLM 비용 모델 (명시)
- 세 프로바이더 공용 API가 아니라 각 계정 개별 과금: 사용자가 `.env`에 **본인의** `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `OPENAI_API_KEY`를 입력.
- 세션 생성 UI에서 **`.env`에 키가 세팅된 프로바이더만 드롭다운에 노출**.
- 하나의 세션은 하나의 프로바이더에 고정(중도 변경 불가 — 컨텍스트·첨부 포맷이 달라지므로).
- 비용은 각 콘솔(Anthropic Console / Google AI Studio / OpenAI Platform)에서 확인.

## 디렉토리 구조
```
threepio/
├── backend/
│   ├── main.py            # FastAPI 라우트, SSE
│   ├── db.py              # SQLite 스키마 + CRUD
│   ├── llm/
│   │   ├── __init__.py    # get_client(provider) 팩토리
│   │   ├── base.py        # LLMClient 추상 인터페이스
│   │   ├── claude.py      # Anthropic 구현
│   │   ├── gemini.py      # Google GenAI 구현
│   │   └── openai_impl.py # OpenAI 구현 + PDF 텍스트 추출 fallback
│   ├── prompts.py         # 시스템/피드백 프롬프트
│   ├── scoring.py         # 세션 종료 피드백·점수 생성
│   └── schemas.py         # Pydantic 모델
├── frontend/
│   ├── index.html
│   ├── app.js
│   └── style.css
├── data/
│   ├── app.db
│   └── uploads/{session_id}/{filename}
├── .env                   # 프로바이더 API 키들
├── requirements.txt
├── environment.yml        # conda env 정의 (선택)
└── README.md
```

## 데이터 모델 (SQLite)
```sql
CREATE TABLE sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  topic TEXT NOT NULL,
  situation TEXT NOT NULL,
  user_role TEXT NOT NULL,
  model_role TEXT NOT NULL,
  llm_provider TEXT NOT NULL,    -- 'claude' | 'gemini' | 'openai'
  llm_model TEXT NOT NULL,       -- 'claude-sonnet-4-6' | 'gemini-2.5-pro' | 'gpt-4o' 등
  created_at TEXT NOT NULL,
  ended_at TEXT,
  feedback_json TEXT             -- {scores, corrections, summary}
);
CREATE TABLE messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id INTEGER NOT NULL REFERENCES sessions(id),
  role TEXT NOT NULL,            -- 'user' | 'assistant'
  source TEXT,                   -- 'voice' | 'text' (user 메시지에 한해 기록, 통계용)
  content TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE attachments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id INTEGER NOT NULL REFERENCES sessions(id),
  filename TEXT NOT NULL,
  mime_type TEXT NOT NULL,
  path TEXT NOT NULL
);
```

## LLM 추상화 ([threepio/backend/llm/base.py](threepio/backend/llm/base.py))
```python
class LLMClient(ABC):
    @abstractmethod
    async def stream_reply(
        self, system: str, history: list[Msg], attachments: list[Attachment]
    ) -> AsyncIterator[str]: ...
    @abstractmethod
    async def one_shot(self, system: str, user: str) -> str: ...
    @property
    @abstractmethod
    def default_model(self) -> str: ...
```

**구현 차이**
- **Claude** ([llm/claude.py](threepio/backend/llm/claude.py)): `anthropic.AsyncAnthropic`. PDF는 `{type:"document", source:{type:"base64",...}}`, 이미지는 `{type:"image", ...}`. 첫 user message 첨부에 `cache_control: ephemeral` 적용.
- **Gemini** ([llm/gemini.py](threepio/backend/llm/gemini.py)): `google.genai` SDK. PDF·이미지 모두 `Part.from_bytes(mime_type=...)`로 첨부. 히스토리는 `contents=[Content(role="user"|"model", parts=[...])]`. 스트림은 `aio.models.generate_content_stream(...)`.
- **OpenAI** ([llm/openai_impl.py](threepio/backend/llm/openai_impl.py)): `openai.AsyncOpenAI` Chat Completions. 이미지는 `{type:"image_url", image_url:{url:"data:..."}}`. **PDF는 지원 안 됨 → `pypdf`로 텍스트 추출 후 system prompt에 `## Attached documents` 섹션으로 임베드**. 긴 문서는 프로바이더별 컨텍스트 한도 감안해 단순 truncate (v1).

## 백엔드 엔드포인트
| Method | Path | 역할 |
|--------|------|------|
| GET | `/api/providers` | `.env`에 키가 설정된 사용 가능 프로바이더·모델 목록 |
| POST | `/api/sessions` | 세션 생성 (title/topic/situation/roles + **llm_provider**) |
| POST | `/api/sessions/{id}/attachments` | multipart 업로드, **복수 파일 지원** (`files: list[UploadFile]`) |
| POST | `/api/sessions/{id}/start` | 시스템프롬프트+첨부→모델의 첫 질문 생성 |
| POST | `/api/sessions/{id}/messages` | 사용자 발화 전송 (body에 `source: 'voice'|'text'` 포함), 응답 SSE 스트림 |
| POST | `/api/sessions/{id}/end` | 세션 종료 + 점수·교정 피드백 생성 및 저장 |
| GET | `/api/sessions` | 세션 목록 |
| GET | `/api/sessions/{id}` | 세션 상세 (메시지·첨부·피드백) |
| GET | `/` · `/static/*` | `frontend/` 정적 서빙 |

**스트리밍**: `StreamingResponse`로 `text/event-stream`, 각 프로바이더의 델타 이벤트를 통일된 `data: {"delta": "..."}\n\n` 포맷으로 릴레이 → 프론트는 토큰 단위 버블 갱신 + 문장 종결 단위 TTS 큐잉.

## 프롬프트 설계 ([threepio/backend/prompts.py](threepio/backend/prompts.py))

**회화 시스템 프롬프트**
```
You are role-playing as "{model_role}" in the following scenario.
Topic: {topic}
Situation: {situation}
The user is role-playing as "{user_role}".

Rules:
- Respond ONLY in natural spoken English.
- Keep each turn to 2–4 sentences — this is a live conversation.
- Ask probing, specific follow-up questions that push the user to elaborate.
- If reference materials (PDFs/images) are attached, ground questions in them.
- Do not break character. Do not translate into Korean.
```
**세션 시작 트리거**: 첫 user message에 `"Please begin by asking me your opening question."` + 첨부 content blocks.

**피드백/채점 프롬프트** ([threepio/backend/scoring.py](threepio/backend/scoring.py))
- 입력: 세션의 모든 user 메시지 (assistant 제외)
- 모델: 해당 세션과 **동일한 프로바이더** 사용
- 반환 JSON (엄격):
```json
{
  "scores": {
    "quality": 0-100,          // 문법·어휘·표현 정확성
    "fluency": 0-100,          // 문장 완결성·자연스러움·망설임 표현 빈도
    "communication": 0-100,    // 의미 전달·주제 적합성·응답 구체성
    "overall": 0-100           // 위 셋의 가중 평균 (각 1/3)
  },
  "summary": "한국어 2–3문장 총평",
  "corrections": [
    {"original": "...", "suggestion": "...", "explanation": "한국어 설명"}
    // 3~4개
  ]
}
```
- 프롬프트 말미에 "반드시 JSON만 출력, 다른 설명 금지" 명시. 파싱: `json.loads` → 실패 시 ```json 펜스 제거 후 재시도 → 여전히 실패 시 `raw_feedback`에 원문 저장.
- **Fluency의 한계 명시**: 텍스트만으로는 진짜 유창성(속도·일시정지) 측정 불가 → 프롬프트에 "문장 완결성, 망설임 표현(uh/um/like 등) 빈도, 자기 수정 빈도로 근사"라고 평가 기준 명시.

## 프론트엔드 흐름 ([threepio/frontend/app.js](threepio/frontend/app.js))

1. **홈 (세션 목록)** — 제목·날짜·프로바이더 뱃지 + "새 세션" 버튼.
2. **새 세션 생성 폼**
   - title, topic, situation, user_role, model_role
   - **LLM 드롭다운**: `/api/providers` 결과로 동적 렌더링 (키 없는 건 disabled + "키 미설정" 힌트)
   - **복수 파일 드래그앤드롭** (PDF·PNG·JPG), 선택된 파일 리스트와 개별 제거 버튼
   - "시작" → 세션 생성 → 첨부 일괄 업로드 → `/start` → 대화 뷰 이동
3. **대화 뷰 (메신저 UI)**
   - assistant 버블(좌) / user 버블(우), 자동 스크롤
   - assistant 스트림 수신 → 텍스트 버블 실시간 갱신 + 문장 단위 `SpeechSynthesisUtterance` 큐잉 재생
   - **두 가지 입력 방식 공존**:
     - 🎤 마이크 버튼: `SpeechRecognition(lang='en-US', continuous=true, interimResults=true)` 토글 → interim transcript를 입력 박스에 실시간 삽입 → 정지 시 자동 미전송(수정 가능), 별도 "전송" 버튼 클릭으로 전송
     - 텍스트 입력 박스: 언제든 직접 타이핑 가능, Enter 또는 "전송" 버튼으로 전송
     - 전송 시 메시지에 `source: 'voice'|'text'` 기록 (마지막 입력 경로 기준)
   - 마이크 권한 거부·브라우저 미지원 시 🎤 버튼 비활성 + 힌트 표시 → 텍스트 입력만으로 동작
   - "세션 종료" 버튼 → `/end` → 로딩 → 피드백 모달에 **점수 차트(4개) + 총평 + 교정 카드 3~4개** 표시
4. **세션 상세 뷰** — 과거 대화 + 점수·교정 전체 조회.

## 구현 순서
1. **환경**: `conda create -n threepio python=3.11 -y` → `conda activate threepio` → `requirements.txt` 작성·설치
2. `backend/db.py` — 스키마 초기화 + CRUD
3. `backend/llm/base.py` + `claude.py` 먼저 → 단일턴→멀티턴→첨부 순으로 수동 검증
4. `backend/main.py` — non-streaming 버전으로 세션·업로드·start·end 엔드포인트 완성, `/docs`로 E2E 확인
5. `gemini.py`·`openai_impl.py` 추가 + PDF 텍스트 추출 fallback
6. `/messages` SSE 스트리밍 전환 (세 프로바이더 델타 포맷 통일)
7. `scoring.py` — 점수+교정 JSON 프롬프트 튜닝 (실제 대화 샘플로 검증)
8. 프론트: 목록 → 생성 폼(프로바이더 드롭다운·복수 업로드) → 대화 UI(음성+텍스트 공존) → 피드백 모달(점수 표시) → 상세 뷰
9. README: conda env 생성·활성화·`.env` 키 설정·실행 명령 정리

## 핵심 파일
- [threepio/backend/main.py](threepio/backend/main.py) — 라우트·SSE
- [threepio/backend/llm/base.py](threepio/backend/llm/base.py) — 공통 인터페이스
- [threepio/backend/llm/claude.py](threepio/backend/llm/claude.py), [gemini.py](threepio/backend/llm/gemini.py), [openai_impl.py](threepio/backend/llm/openai_impl.py) — 프로바이더별 구현
- [threepio/backend/scoring.py](threepio/backend/scoring.py) — 점수·교정 생성
- [threepio/backend/prompts.py](threepio/backend/prompts.py) — 프롬프트
- [threepio/frontend/app.js](threepio/frontend/app.js) — UI 상태·STT/TTS·SSE 소비

## Verification
**1. 환경 세팅**
- `conda create -n threepio python=3.11 -y && conda activate threepio`
- `pip install -r requirements.txt`
- `.env`에 최소 하나 이상의 API 키 설정

**2. 백엔드 단위**
- `uvicorn backend.main:app --reload --port 8000`
- `/docs`에서: `/api/providers` → 키 설정 된 프로바이더만 노출되는지 / 세션 생성 → **PDF 2개 + 이미지 1개 업로드** → `/start` → `/messages` 2~3턴 → `/end` → 반환 JSON에 `scores`(4개 지표)·`corrections`(3~4개) 포함 확인

**3. 프론트 E2E (Chrome)**
- 홈 → 새 세션 (provider=Claude로 먼저) → 복수 파일 드랍 → 시작
- 첫 질문이 텍스트+음성으로 재생
- 🎤로 영어 답변 → transcript 확인 → 전송 → 2~3턴
- 중간에 🎤 대신 **텍스트로 타이핑 전송**도 정상 동작하는지
- 세션 종료 → 피드백 모달에 점수(0–100, 4개)+총평+교정 3~4개 확인
- 같은 플로우를 provider=Gemini, provider=OpenAI로 각각 반복 (OpenAI는 PDF 텍스트 추출 결과가 응답에 반영되는지)
- 홈으로 돌아가 세션 상세 재열람

**4. 엣지 케이스**
- `.env`에 하나의 키만 있을 때 드롭다운에 하나만 노출
- 첨부 없는 세션 정상 동작
- 마이크 권한 거부 시 텍스트 입력만으로 완주 가능
- 긴 assistant 응답 TTS 끊김 없음
- 종료된 세션에 메시지 재전송 시도 시 400

## Out of Scope (v1)
- 인증·멀티유저 (로컬 단일 사용자)
- 모바일 반응형
- Firefox/Safari Web Speech API 한계 (Chromium 전용 안내)
- 진짜 오디오 기반 유창성 측정 (텍스트 근사로 대체)
- OpenAI의 PDF 장문 처리 고도화 (v1은 단순 truncate)
- 대화 도중 LLM 변경
