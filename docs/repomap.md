# llm-mirror — Repomap

## Module boundaries

```
main.py (entry point)
   ├── packages/ (scenario packages: Package protocol, DebatePackage)
   │    └── debate/ (debate scenario: personas, system prompt, rendering)
   ├── prompt.py (pure renderer: Message, speaker_label, render_transcript, render_tail, strip_reply)
   ├── session.py (JSONL store, resume, slugify)
   ├── client.py (HTTP oMLX client)
   ├── app.py (state machine, worker thread, package integration)
    └── tui.py (Textual TUI, command dispatch)
```

## Public API signatures

### packages/__init__.py

```python
@runtime_checkable
class Package(Protocol):
    @property
    def name(self) -> str
    @property
    def personas(self) -> dict[str, str]
    @property
    def system_prompt(self) -> str
    def render_transcript(self, messages: Sequence[Message]) -> str
    def render_tail(self, speaker: str, opening: bool) -> str
    @property
    def seed_topics(self) -> list[str]
    def next_speaker(self, current: str) -> str

def load_packages() -> dict[str, Package]
```

### packages/debate/__init__.py

```python
class DebatePackage:
    def __init__(self, free: bool = False) -> None
    @property
    def name(self) -> str
    @property
    def personas(self) -> dict[str, str]
    @property
    def system_prompt(self) -> str
    def render_transcript(self, messages: Sequence[Message]) -> str
    def render_tail(self, speaker: str, opening: bool) -> str
    @property
    def seed_topics(self) -> list[str]
    def next_speaker(self, current: str) -> str
```

### prompt.py

```python
class Message:
    speaker: str
    content: str

def speaker_label(speaker: str) -> str
def render_transcript(messages: Sequence[Message]) -> str
def render_tail(speaker: str, opening: bool) -> str
def strip_reply(content: str, speaker: str) -> str
```

### session.py

```python
class Sampling:
    temperature: float
    max_tokens: int
    frequency_penalty: float
    presence_penalty: float

class TurnUsage:
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int

class SessionMeta:
    model: str
    base_url: str
    package_name: str
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
    def __init__(self, client, store, state, package, max_turns=0, ctx_guard_pct=0.9) -> None
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
def _format_message(msg: Message) -> Text

class Tui(App):
    def __init__(self, app: MirrorApp, store: SessionStore, session_id: str, model: str) -> None
    def compose(self) -> ComposeResult
    def on_mount(self) -> None
    @work(thread=True)
    async def refresh_worker(self) -> None
    def _schedule_ui_update(self, data: dict) -> None
    def action_pause(self) -> None
    def action_resume(self) -> None
    def action_save(self) -> None
    def action_quit(self) -> None
    async def on_input_submitted(self, event: Input.Submitted) -> None
```
