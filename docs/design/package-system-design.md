# Package System — MVP 0 Design

- Type: feature (refactor + extension)
- Status: implemented
- Design doc: this file. Roadmap ticket: `roadmap/features/package-system-mvp-0.md`

## Problem

`personas.py` and `prompt.py` are hardwired to one conversation style: two personas (Echo, Mirror) in a debate format. Every new scenario type — roleplay, improv, collaboration — requires modifying these same files, which breaks the byte-identity invariant, forces test changes across all modules, and creates coupling between unrelated conversation styles. There is no way to add a new scenario without touching core rendering logic.

## Verified environment facts

| Fact | Value | How verified |
|---|---|---|
| Current persona system | `personas.py` exports `ECHO_CARD`, `MIRROR_CARD`, `SCENARIO_GROUNDED`, `SCENARIO_FREE`, `SEED_TOPICS` | source read |
| Prompt rendering | `prompt.py` exports `render_system`, `render_transcript`, `render_tail`, `render_user_message` — all call into `personas.py` constants | source read |
| App prompt wiring | `app.py:_run_turn()` calls `render_system()` and `render_user_message()` directly, passing `self._state.meta.echo_card` and `self._state.meta.mirror_card` | source read `app.py:182-193` |
| CLI persona override | `main.py` accepts `--echo-prompt`/`--mirror-prompt` and passes them to `SessionMeta` as card overrides | source read `main.py:157-158` |
| Speaker rotation | `app.py:249` hardcodes `"mirror" if self._state.next_speaker == "echo" else "echo"` | source read |
| Byte-identity tests | `tests/test_prompt.py` asserts exact output of `render_system`, `render_tail`, `render_transcript` | source read |
| Plugin discovery | Python entry points via `importlib.metadata.entry_points()` are the de facto standard for cross-package plugin discovery | research |

## Target state

A `packages` module provides a `Package` interface. Each package bundles persona cards, system prompt, rendering logic, and seed topics for one conversation style. Packages are discovered via Python entry points. The app loads a package by name (via `--scenario`), and all prompt rendering flows through the package. The existing debate scenario becomes the default package. New packages are added as separate modules without touching `personas.py`, `prompt.py`, `app.py`, or `tui.py`.

## Final decisions

### D1 — One `Package` protocol, five required methods

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
```

Each method returns a string (the rendered prompt fragment). The app calls these methods instead of the standalone functions in `prompt.py`. The protocol is minimal: adding a method breaks every existing package. All methods are required — no optional methods, no defaults.

**Rejected: optional methods with defaults.** The research confirms this is the #1 source of plugin breakage. If a future version needs a new hook (e.g., `on_injection`), it will be a breaking change that requires package updates — which is acceptable for MVP 0 since all packages ship with the core.

**Rejected: separate `Persona` dataclass.** Personas are just name→card-string mappings. A `dict[str, str]` is sufficient. A richer Persona type (with voice hints, background, constraints) belongs in a future version when scenario types actually need it.

### D2 — Entry-point-based discovery, no stevedore, no pluggy

Packages register via `pyproject.toml` entry points under the group `"llm_mirror.packages"`:

```toml
[project.entry-points."llm_mirror.packages"]
debate = "llm_mirror.packages.debate:DebatePackage"
```

Discovery uses `importlib.metadata.entry_points(group="llm_mirror.packages")` directly. The loader returns `dict[str, Package]`.

**Rejected: stevedore.** Stevedore wraps entry points with manager classes (Driver, Extension, Hook). This project only needs "load by name" — a single package is selected, not iterated or dispatched. Stevedore adds a dependency and abstraction layer that provides no value for this use case.

**Rejected: pluggy.** Pluggy provides hook-based plugin systems (event-driven, N:1 callbacks). This is a strategy pattern (pick one package, run it). Hook-based design is overkill and introduces unnecessary coupling between packages and the host.

**Rejected: namespace packages.** Namespace packages (`llm_mirror.packages` as a shared namespace) add complexity around `__init__.py` handling and `setuptools.find_packages()` incompatibility. Entry points alone solve the discovery problem without namespace package machinery.

### D3 — The debate package is extracted from existing code

The current `personas.py` + `prompt.py` logic becomes `packages/debate/__init__.py`:

```
src/llm_mirror/packages/
    __init__.py          # Package protocol, loader, registry
    debate/
        __init__.py      # DebatePackage: system prompt, personas, rendering, seeds
```

`personas.py` is removed. Its constants (`ECHO_CARD`, `MIRROR_CARD`, `SEED_TOPICS`, `SCENARIO_INTRO`, `GROUNDING_CLAUSES`) move into the debate package. `prompt.py`'s standalone functions (`render_system`, `render_transcript`, `render_tail`, `render_user_message`) are replaced by package method calls.

**What stays in `prompt.py`:** `Message` dataclass, `speaker_label()`, `strip_reply()`. These are format utilities unrelated to scenario logic. `render_user_message()` is removed — the app constructs the user message by concatenating `package.render_transcript()` + `package.render_tail()` directly.

### D4 — `SessionMeta.scenario` becomes `SessionMeta.package_name`

`SessionMeta.scenario` (currently `"grounded"` or `"free"`) is replaced by `SessionMeta.package_name` (currently `"debate"`). The `--free` flag is retained for backward compatibility but maps to `--scenario debate --variant free` internally.

**Backward compatibility:** `load_session()` in `session.py` reads `scenario` from existing JSONL files and maps `"grounded"` → `"debate"` and `"free"` → `"debate"` with a variant flag stored in the session event. This ensures resumed sessions work without migration.

**Rejected: keep `scenario` as-is.** The current `"grounded"`/`"free"` distinction is a debate-package-specific concept (grounding clauses vs no grounding clauses). It does not generalize to other scenario types. Renaming to `package_name` is the clean break.

### D5 — CLI: `--scenario` replaces `--free`; `--echo-prompt`/`--mirror-prompt` still work

```
--scenario NAME    Select package by name (default: "debate")
--free             Deprecated: maps to --scenario debate --variant free
--echo-prompt TXT  Override Echo persona card (package-dependent)
--mirror-prompt TXT  Override Mirror persona card (package-dependent)
```

When `--echo-prompt` or `--mirror-prompt` is provided, the override replaces the persona card in the package's `personas` dict at runtime. The package itself is unchanged — overrides are applied in `main.py` after package loading.

**Rejected: persona overrides at the package level.** Persona card overrides are a CLI concern, not a package concern. The package provides defaults; the CLI layer applies user overrides.

### D6 — Speaker rotation moves from app.py into the package

`app.py:249` (`"mirror" if self._state.next_speaker == "echo" else "echo"`) is replaced by `package.next_speaker(self._state.next_speaker)`. The debate package returns the alternating echo↔mirror pattern. Future packages (e.g., improv with audience injection) can implement different rotation logic.

**Rejected: keep rotation in app.py.** Rotation logic is scenario-dependent. A roleplay package might need asymmetric turns (one persona speaks twice in a row). A collaboration package might need no rotation at all (user drives). The package owns its turn structure.

### D7 — TUI shows package name in status bar

The status bar appends `| package: <name>` after the session ID. No new UI elements — just metadata display.

### D8 — `personas.py` is removed, not deprecated

`personas.py` is deleted. All imports of `P.ECHO_CARD`, `P.MIRROR_CARD`, `P.SEED_TOPICS`, `P.SCENARIO_GROUNDED`, `P.SCENARIO_FREE`, `P.GROUNDING_CLAUSES` are replaced with package imports. `prompt.py`'s import of `llm_mirror.personas as P` is removed.

**Rejected: keep `personas.py` as a compatibility shim.** Dead code accumulates. Since this is a pre-1.0 project with no external dependents, removal is safe and cleaner than maintaining a shim.

## What is unchanged

| Component | Why unchanged |
|---|---|
| `client.py` | HTTP oMLX client — no prompt logic |
| `session.py` (except `scenario` → `package_name` rename) | JSONL store, resume, slugify, markdown render — no prompt logic |
| `app.py` state machine (RUNNING/PAUSED/STOPPED, worker thread, injection queue, context guard, max turns) | Conversation control is scenario-agnostic |
| `app.py` telemetry (SessionStats, per_speaker, token tracking) | Telemetry is scenario-agnostic |
| `tui.py` core (Textual app, RichLog, command dispatch, injection parsing, refresh worker) | UI is scenario-agnostic; only status bar text changes |
| `tui.py` `@echo:`/`@mirror:` injection targeting | Targeting uses speaker names from the package's persona keys |
| `prompt.py` `Message`, `speaker_label()`, `strip_reply()` | Format utilities, not scenario logic |
| `tests/test_app.py`, `tests/test_client.py`, `tests/test_session.py`, `tests/test_tui.py` | No changes to tested behavior |

## Interface contracts

### `Package` protocol (final)

```python
class Package(Protocol):
    @property
    def name(self) -> str:
        """Machine-readable package identifier, e.g. 'debate'."""

    @property
    def personas(self) -> dict[str, str]:
        """Speaker key → persona card string. Keys match speaker names used in messages."""

    @property
    def system_prompt(self) -> str:
        """Full system prompt text. Includes intro, persona cards, and rules."""

    def render_transcript(self, messages: Sequence[Message]) -> str:
        """Render conversation history as plain text with speaker labels."""

    def render_tail(self, speaker: str, opening: bool) -> str:
        """Tail directive telling the model what to write next."""

    @property
    def seed_topics(self) -> list[str]:
        """List of seed topic strings for new sessions."""

    def next_speaker(self, current: str) -> str:
        """Return the next speaker given the current one. e.g. 'echo' → 'mirror'."""
```

### Entry point group

```
llm_mirror.packages
```

Each entry point value is `module:Class` where `Class` is a `Package` implementation.

### `SessionMeta` field change

| Before | After |
|---|---|
| `scenario: str` (`"grounded"` or `"free"`) | `package_name: str` (e.g. `"debate"`) |

`load_session()` maps legacy `scenario` values:
- `"grounded"` → `package_name="debate"`
- `"free"` → `package_name="debate"` (with variant tracking if needed)

### `render_user_message()` removal

The app constructs the user message directly:

```python
# Before (app.py:193)
user = render_user_message(self._state.messages, opening)

# After
transcript = package.render_transcript(self._state.messages)
tail = package.render_tail(
    self._state.next_speaker if not opening else next(iter(package.personas)),
    opening,
)
user = transcript + "\n\n" + tail if transcript else tail
```

## Open questions

### Resolved: variant support within a package

The debate package's `system_prompt` checks a `self._free` boolean flag set at construction time. `--free` sets this flag. No `variant` field on `SessionMeta`. If a future package needs named variants, that design is deferred.

### Resolved: `speaker_label()` scope

`speaker_label()` stays in `prompt.py` as a global utility. Speaker labels are display formatting with a fixed 3-entry mapping. Moving it into the package adds a method call with no behavioral difference.

### Resolved: backward-compatible `--scenario` default

`llm-mirror` defaults to `--scenario debate` explicitly. Auto-detection is fragile — a third-party package should not change default behavior. Explicit default is predictable and matches current behavior.

## Rejected alternatives

### Reject: make `prompt.py` functions package-agnostic by passing persona strings as parameters

The current `render_system(echo_card, mirror_card, free)` signature already does this. Making it fully generic (passing all rendering logic as parameters) creates a dependency-injection anti-pattern: the app becomes a glue layer passing strings between functions, and the byte-identity invariant becomes harder to test because the rendering logic is scattered across multiple call sites. Bundling all rendering into the package keeps the contract tight and testable.

### Reject: use YAML/JSON for prompt templates

Tools like PromptTemplateManager and PAL use YAML for prompt storage. This adds a dependency, a parsing layer, and indirection for a project where prompt templates are short, stable, and version-controlled in Python. Jinja2 templating (if needed) can be handled inline in Python strings. YAML prompt management is overkill for MVP 0.

### Reject: make personas independently swappable across packages

The research on persona-prompt mismatch confirms that personas and scenarios are deeply coupled — the system prompt assumes a persona dynamic, the transcript formatting assumes consistent speaker naming, and the byte-identity tests assume fixed persona cards. Making personas independently swappable creates an N×M test surface and unpredictable behavior. Personas belong inside packages; future versions can add a persona registry if there's demand.

### Reject: use `__init_subclass__` for automatic package registration

`__init_subclass__` provides zero-config registration for plugins in the same codebase. However, it doesn't support cross-package discovery (third-party pip-installable packages), which is the whole point of entry points. Using both `__init_subclass__` and entry points adds confusion about which mechanism applies when. Stick with entry points only.
