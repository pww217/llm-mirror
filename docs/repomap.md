# llm-mirror — Repomap

## Module boundaries

```
main.py (entry point)
  ├── personas.py (constants)
  ├── prompt.py (pure renderer)
  ├── session.py (JSONL store, resume, slugify)
  ├── client.py (HTTP oMLX client)
  ├── app.py (state machine, worker thread)
  └── tui.py (rich TUI, command dispatch)
```

## Public API signatures

### personas.py

```python
ECHO_CARD: str
MIRROR_CARD: str
SCENARIO_GROUNDED: str
SCENARIO_FREE: str
SEED_TOPICS: list[str]
```

### prompt.py

```python
@dataclass(frozen=True)
class Message:
    speaker: str
    content: str

def speaker_label(speaker: str) -> str
def render_system(echo_card: str, mirror_card: str, free: bool) -> str
def render_transcript(messages: Sequence[Message]) -> str
def render_tail(speaker: str, opening: bool) -> str
def render_user_message(messages: Sequence[Message], opening: bool) -> str
def strip_reply(content: str, speaker: str) -> str
```

### session.py

```python
@dataclass(frozen=True)
class Sampling:
    temperature: float
    max_tokens: int
    frequency_penalty: float
    presence_penalty: float

@dataclass(frozen=True)
class TurnUsage:
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int

@dataclass(frozen=True)
class SessionMeta:
    model: str
    base_url: str
    scenario: str
    echo_card: str
    mirror_card: str
    sampling: Sampling
    seed: str | None
    max_model_len: int
    thinking: bool

class SessionState:
    meta: SessionMeta
    messages: list[Message]
    next_speaker: str

class SessionStore:
    def __init__(self, path: Path) -> None
    @property
    def path(self) -> Path
    def append_event(self, event: dict) -> None
    def write_markdown(self, state: SessionState) -> None
    def close(self) -> None

def slugify(seed: str | None) -> str
def new_session_path(session_dir: Path, seed: str | None) -> Path
def load_session(path: Path) -> SessionState
```

### client.py

```python
class OmlxClientError(Exception)
class TransientOmlxClientError(Exception)

@dataclass(frozen=True)
class ChatRequest:
    model: str
    system: str
    user: str
    temperature: float
    max_tokens: int
    frequency_penalty: float
    presence_penalty: float
    thinking: bool

@dataclass(frozen=True)
class TurnResult:
    content: str
    usage: TurnUsage
    latency_ms: int

class OmlxClient:
    def __init__(self, base_url: str) -> None
    def health(self) -> dict
    def models(self) -> list[dict]
    def chat(self, req: ChatRequest) -> TurnResult
```

### app.py

```python
class AppStatus(Enum):
    RUNNING = auto()
    PAUSED = auto()
    STOPPED = auto()

@dataclass
class SessionStats:
    turns: int
    per_speaker: dict[str, int]
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    cache_hit_pct: float
    mean_latency_ms: float
    duration_s: float

class MirrorApp:
    def __init__(self, client, store, state, max_turns=0, ctx_guard_pct=0.9) -> None
    def status(self) -> AppStatus
    def start(self) -> None
    def pause(self) -> None
    def resume(self) -> None
    def quit(self) -> None
    def save(self) -> None
    def inject(self, text: str, target: str = "ambient") -> None
    def stats(self) -> SessionStats
    @property
    def last_turn(self) -> SessionStats | None
```

### tui.py

```python
@dataclass(frozen=True)
class ParsedInput:
    command: str | None
    injection_target: str
    content: str

def parse_input(raw: str) -> ParsedInput

class Tui:
    def __init__(self, app: MirrorApp, store: SessionStore, session_id: str, model: str) -> None
    def run(self) -> None
    def _refresh_loop(self) -> None
    def _on_refresh(self) -> None
```
