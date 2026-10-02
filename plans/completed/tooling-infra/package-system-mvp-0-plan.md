# Package System MVP 0 — Plan

## Design Reference

`docs/design/package-system-design.md`

## Phase summary

Three phases. Phase 01 establishes the `Package` protocol and extracts the existing debate scenario into `packages/debate/`. Phase 02 wires the app, CLI, session store, and TUI to use packages. Phase 03 deletes `personas.py`, cleans up `prompt.py`, and updates tests. Each phase is independently verifiable with `uv run pytest` and `uv run llm-mirror --help`.

---

## 01 — Package protocol + debate package extraction

**What:** Create `packages/__init__.py` with the `Package` protocol and entry-point loader. Create `packages/debate/__init__.py` with `DebatePackage` implementing the protocol. Add tests.

**Files:**
- `src/llm_mirror/packages/__init__.py` (new)
- `src/llm_mirror/packages/debate/__init__.py` (new)
- `tests/test_packages.py` (new)

**Task 01-1: `packages/__init__.py` — Package protocol and loader**

Create `src/llm_mirror/packages/__init__.py` with:

```python
class Package(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def personas(self) -> dict[str, str]: ...
    @property
    def system_prompt(self) -> str: ...
    def render_transcript(self, messages: Sequence[Message]) -> str: ...
    def render_tail(self, speaker: str, opening: bool) -> str: ...
    @property
    def seed_topics(self) -> list[str]: ...
    def next_speaker(self, current: str) -> str: ...

def load_packages() -> dict[str, Package]:
    eps = entry_points(group="llm_mirror.packages")
    return {ep.name: ep.load() for ep in eps}
```

**Why:** This is the interface contract. Every package implements it. The loader discovers packages via entry points.

**Validation:** No tests yet (no packages registered). The file compiles (`python -c "from llm_mirror.packages import Package, load_packages"`).

**Task 01-2: `packages/debate/__init__.py` — DebatePackage**

Create `src/llm_mirror/packages/debate/__init__.py` with:

```python
class DebatePackage:
    """Debate scenario: two personas explore a topic in alternating turns."""

    def __init__(self, free: bool = False) -> None:
        self._free = free

    @property
    def name(self) -> str:
        return "debate"

    @property
    def personas(self) -> dict[str, str]:
        return {
            "echo": "warm, curious, and generative. Proposes ideas, explores possibilities, builds on what others said, asks interesting questions.",
            "mirror": "skeptical and precise. Examines claims, points out weaknesses and hidden assumptions, offers counterexamples, disagrees when warranted. Not hostile — rigorous.",
        }

    @property
    def system_prompt(self) -> str:
        intro = "This is an ongoing conversation between two AI participants, Echo and Mirror, occasionally joined by a human, \"User\". They take turns in strict rotation: Echo, Mirror, Echo, Mirror, and so on. Each transcript line is one speaker's message, labeled with their name. There is no moderator; the conversation never ends and is never summarized or wrapped up.\n\n"
        cards = "Echo: " + self.personas["echo"] + "\nMirror: " + self.personas["mirror"] + "\n\n"
        rules = "Stay in character as the named speaker. Advance the topic: introduce a new idea, question, perspective, or example.\n"
        if not self._free:
            rules += "Stay on the conversation's topic.\nDo not comment on being an AI, on the format, or on the conversation itself.\n"
        rules += "Never conclude, sign off, or say goodbye.\n"
        return intro + cards + rules

    def render_transcript(self, messages: Sequence[Message]) -> str:
        return "\n".join(
            f"{msg.speaker.capitalize()}: {msg.content}" for msg in messages
        )

    def render_tail(self, speaker: str, opening: bool) -> str:
        label = speaker.capitalize()
        if opening:
            return f"This is the opening of the conversation. Write only {label}'s message text (no name label), in character."
        return f"Write only {label}'s next message text (no name label), in character."

    @property
    def seed_topics(self) -> list[str]:
        return [
            "whether cities should ban private cars downtown",
            "whether chess is a solved game in principle",
            "what makes a scientific instrument trustworthy",
            "whether remote work weakens mentorship",
            "whether analog synthesizers still matter",
            "whether AI-generated art should be considered real art",
            "whether space mining is ethically justified",
            "whether social media has been net positive for democracy",
            "whether standardized testing measures student ability",
            "whether open-source software is more secure than proprietary",
            "whether nuclear energy is the climate solution",
            "whether the four-day workweek is economically viable",
            "whether space exploration deserves current funding levels",
            "whether universal basic income would work at scale",
            "whether online education matches in-person learning",
            "whether genetic engineering of humans should be permitted",
            "whether copyright terms are too long in the digital age",
            "whether public libraries remain essential in the internet era",
            "whether fast fashion is a moral issue",
            "whether the gig economy exploits workers",
            "whether the death penalty is ever justified",
            "whether the metaverse is a useful concept",
            "whether vaccine mandates respect bodily autonomy",
            "whether space tourism is a waste of resources",
            "whether big tech has too much power over society",
            "whether the arts deserve more public funding",
            "whether plastic bans actually help the environment",
            "whether animal testing has a place in modern science",
            "whether the military should control artificial intelligence",
            "whether the concept of privacy is dead in the digital age",
        ]

    def next_speaker(self, current: str) -> str:
        return "mirror" if current == "echo" else "echo"
```

**Why:** This is the extracted debate scenario. It contains all the logic that was previously in `personas.py` and `prompt.py`'s `render_system`. The `free` flag controls grounding clauses.

**Validation:** `uv run python -c "from llm_mirror.packages.debate import DebatePackage; p = DebatePackage(); assert p.name == 'debate'; assert 'Stay on the conversation' in p.system_prompt"`

**Task 01-3: Tests for package protocol and debate package**

Create `tests/test_packages.py` with:

- `TestDebatePackage.test_name` — `DebatePackage().name == "debate"`
- `TestDebatePackage.test_personas` — two entries, keys `"echo"` and `"mirror"`, card text matches current `ECHO_CARD`/`MIRROR_CARD`
- `TestDebatePackage.test_system_prompt_grounded` — contains `SCENARIO_INTRO` text, both persona cards, grounding clauses
- `TestDebatePackage.test_system_prompt_free` — contains intro and cards, excludes grounding clauses
- `TestDebatePackage.test_render_transcript` — empty list → `""`, single message → `"Echo: hello"`, multi → joined with newlines
- `TestDebatePackage.test_render_tail_opening` — `"This is the opening..."`
- `TestDebatePackage.test_render_tail_regular` — `"Write only Echo's next message..."`
- `TestDebatePackage.test_next_speaker` — `"echo"` → `"mirror"`, `"mirror"` → `"echo"`
- `TestDebatePackage.test_seed_topics_count` — 30 topics
- `TestDebatePackage.test_seed_topics_unique` — no duplicates
- `TestDebatePackage.test_byte_identity_system_prompt` — two calls to `system_prompt` return identical strings

**Why:** Byte-identity tests ensure the extracted package produces identical output to the old code. This is the regression safety net.

**Validation:** `uv run pytest tests/test_packages.py -v`

---

## 02 — Wire the app to use packages

**What:** Update `session.py`, `app.py`, `main.py`, and `tui.py` to use the package system. Add `--scenario` CLI flag. Migrate `SessionMeta.scenario` to `SessionMeta.package_name`.

**Files:**
- `src/llm_mirror/session.py` (modify)
- `src/llm_mirror/app.py` (modify)
- `src/llm_mirror/main.py` (modify)
- `src/llm_mirror/tui.py` (modify)
- `tests/test_session.py` (modify)
- `tests/test_app.py` (modify)

**Task 02-1: `session.py` — `SessionMeta.scenario` → `package_name`, legacy mapping**

Rename `SessionMeta.scenario` to `SessionMeta.package_name`. Update `SessionMeta.__init__` signature:

```python
class SessionMeta:
    def __init__(
        self,
        model: str,
        base_url: str,
        package_name: str,  # was: scenario: str
        echo_card: str,
        mirror_card: str,
        sampling: Sampling,
        seed: str | None,
        max_model_len: int,
        thinking: bool = True,
    ) -> None:
        ...
        self.package_name = package_name  # was: self.scenario = scenario
        ...
```

Update `load_session()` to map legacy `scenario` values from JSONL:

```python
# In load_session(), when reading the session event:
scenario_event = event.get("scenario")
if scenario_event == "grounded":
    package_name = "debate"
elif scenario_event == "free":
    package_name = "debate"
else:
    package_name = scenario_event or "debate"
```

Update `SessionStore.write_markdown()` to display `package_name` instead of `scenario` in the markdown header.

**Why:** This is the data model change. Legacy sessions must resume correctly.

**Validation:** `uv run pytest tests/test_session.py -v` — `load_session` on an existing JSONL file with `"scenario": "grounded"` produces `meta.package_name == "debate"`.

**Task 02-2: `app.py` — use package methods, `next_speaker` from package**

In `MirrorApp.__init__`, add a `package: Package` parameter. Store `self._package`.

In `_run_turn()`, replace:

```python
# Before (app.py:182-193)
if self._state.meta.scenario == "free":
    system = ""
else:
    system = render_system(
        self._state.meta.echo_card,
        self._state.meta.mirror_card,
        False,
    )
if self._state.meta.scenario == "free" and self._state.meta.seed is None:
    user = ""
else:
    user = render_user_message(self._state.messages, opening)
```

With:

```python
# After
system = self._package.system_prompt
transcript = self._package.render_transcript(self._state.messages)
tail = self._package.render_tail(
    self._state.next_speaker if not opening else next(iter(self._package.personas)),
    opening,
)
user = transcript + "\n\n" + tail if transcript else tail
```

Replace the hardcoded speaker flip at `app.py:249`:

```python
# Before
self._state.next_speaker = "mirror" if self._state.next_speaker == "echo" else "echo"

# After
self._state.next_speaker = self._package.next_speaker(self._state.next_speaker)
```

**Why:** The app delegates all prompt rendering to the package. Speaker rotation is package-defined.

**Validation:** `uv run llm-mirror --scenario debate --no-seed --headless --turn-delay 0.5` runs a conversation without errors.

**Task 02-3: `main.py` — `--scenario` flag, package loading, backward compat**

Add `--scenario` argument:

```python
parser.add_argument("--scenario", type=str, default="debate", help="Scenario package name (default: debate)")
```

Keep `--free` for backward compatibility:

```python
parser.add_argument("--free", action="store_true", default=False, help="[deprecated] Use --scenario debate")
```

After loading the client, load packages and select the active one:

```python
from llm_mirror.packages import load_packages

packages = load_packages()
scenario_name = args.scenario
if scenario_name not in packages:
    print(f"Unknown scenario: {scenario_name}. Available: {', '.join(packages.keys())}", file=sys.stderr)
    return 2
package = packages[scenario_name]

# Handle --free override
if args.free:
    # If the package supports free mode, configure it
    if hasattr(package, '_free'):
        package._free = True
```

Update `SessionMeta` construction to use `package_name=scenario_name` and use the package's personas for default cards:

```python
# Before
echo_card=args.echo_prompt or P.ECHO_CARD,
mirror_card=args.mirror_prompt or P.MIRROR_CARD,

# After
scenario_name=scenario_name,
echo_card=args.echo_prompt or package.personas.get("echo", ""),
mirror_card=args.mirror_prompt or package.personas.get("mirror", ""),
```

Update seed topic selection:

```python
# Before
seed = random.choice(P.SEED_TOPICS)

# After
seed = random.choice(package.seed_topics)
```

Update session event persistence to store `package_name` instead of `scenario`:

```python
# In the session event:
"package_name": meta.package_name,  # was: "scenario": meta.scenario
```

Keep `meta.scenario` in the session event for backward-compatible resume (write both):

```python
"scenario": scenario_name,  # legacy, for load_session mapping
"package_name": scenario_name,
```

**Why:** This is the CLI integration point. Users select scenarios via `--scenario`. `--free` still works. New sessions store `package_name`.

**Validation:**
- `uv run llm-mirror --help` shows `--scenario` and `--free`
- `uv run llm-mirror --scenario debate --no-seed --headless --turn-delay 0.5` runs
- `uv run llm-mirror --free --no-seed --headless --turn-delay 0.5` runs (free mode)
- `uv run llm-mirror --scenario nonexistent` prints error and exits non-zero

**Task 02-4: `tui.py` — show package name in status bar**

In `_schedule_ui_update()`, add package name to the status bar:

```python
# After the session_id part:
parts.append(f"scenario {self._app._state.meta.package_name if self._app._state else 'debate'}")
```

**Why:** Users need to see which scenario package is active.

**Validation:** Status bar shows `debate` after starting a session.

**Task 02-5: Update `tests/test_app.py` and `tests/test_session.py`**

Update `tests/test_app.py`:
- Any test that references `scenario="grounded"` or `scenario="free"` → `package_name="debate"`
- Any test that imports from `llm_mirror.personas` → import from `llm_mirror.packages.debate`

Update `tests/test_session.py`:
- Any test that references `scenario` field on `SessionMeta` → `package_name`
- Test `load_session` legacy mapping: create a JSONL with `"scenario": "grounded"`, verify `meta.package_name == "debate"`

**Why:** Tests must reflect the new field name and package-based architecture.

**Validation:** `uv run pytest tests/test_app.py tests/test_session.py -v`

---

## 03 — Clean up old code + update tests

**What:** Delete `personas.py`. Remove `render_user_message()` and the `personas` import from `prompt.py`. Update `tests/test_prompt.py`. Delete `tests/test_personas.py`. Verify nothing imports `personas.py`.

**Files:**
- `src/llm_mirror/personas.py` (delete)
- `src/llm_mirror/prompt.py` (modify)
- `tests/test_prompt.py` (modify)
- `tests/test_personas.py` (delete)

**Task 03-1: Delete `personas.py`**

Delete `src/llm_mirror/personas.py`.

**Why:** All constants have moved to `packages/debate/`.

**Validation:** `grep -r "import.*personas" src/` returns nothing. `grep -r "from.*personas" src/` returns nothing.

**Task 03-2: Clean up `prompt.py`**

Remove:
- `import llm_mirror.personas as P` (line 6)
- `render_system()` function (lines 21-27)
- `render_user_message()` function (lines 48-58)

Keep:
- `Message` class
- `speaker_label()` function
- `render_transcript()` function
- `render_tail()` function
- `strip_reply()` function

**Why:** These functions are now provided by the package. Only format utilities remain in `prompt.py`.

**Validation:** `uv run python -c "from llm_mirror.prompt import Message, speaker_label, render_transcript, render_tail, strip_reply"` works. `uv run python -c "from llm_mirror.prompt import render_system"` raises `ImportError`.

**Task 03-3: Update `tests/test_prompt.py`**

Remove:
- `TestRenderSystem` class (all tests moved to `test_packages.py`)
- `TestRenderUserMessage` class (rendered by package, no standalone function)

Update:
- `TestRenderTranscript.test_multiple_messages` — the transcript format changed: `speaker.capitalize()` instead of `speaker_label()`. The `speaker_label()` function still produces the same output (`"echo"` → `"Echo"`), so no change needed. Verify.
- `TestRenderTail` tests — `render_tail()` in `prompt.py` still exists and produces the same output. Verify tests pass.

**Why:** Tests must reflect what's actually in `prompt.py`.

**Validation:** `uv run pytest tests/test_prompt.py -v`

**Task 03-4: Delete `tests/test_personas.py`**

Delete `tests/test_personas.py`. All persona tests are in `tests/test_packages.py`.

**Why:** `personas.py` no longer exists.

**Validation:** `uv run pytest tests/ -v` — all tests pass, no references to `test_personas`.

**Task 03-5: Final verification**

Run:
- `uv run ruff check .` — clean
- `uv run pytest` — all pass
- `uv run llm-mirror --help` — shows `--scenario` and `--free`
- `uv run llm-mirror --no-seed --headless --turn-delay 0.5` — runs a conversation for 3 turns, prints output

**Why:** End-to-end verification that the refactor is complete and the app works.

**Validation:** All four commands succeed with no errors.

---

## Dependency graph

```
01 → 02 → 03
```

- Phase 01 has no dependencies.
- Phase 02 depends on Phase 01 (needs the package to exist).
- Phase 03 depends on Phase 02 (needs the app wired before cleanup).

Each phase is independently executable and testable.
