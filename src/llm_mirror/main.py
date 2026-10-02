from __future__ import annotations

import argparse
import json
import logging
import random
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from llm_mirror.app import MirrorApp
from llm_mirror.client import OmlxClient, OmlxClientError
from llm_mirror.packages import load_packages
from llm_mirror.prompt import Message
from llm_mirror.session import (
    Sampling,
    SessionMeta,
    SessionState,
    SessionStore,
    load_session,
    new_session_path,
)
from llm_mirror.tui import Tui


def _setup_logging(log_level: str) -> None:
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    handler = RotatingFileHandler(
        log_dir / "mirror.log",
        maxBytes=1_048_576,  # 1 MB
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), "INFO"),
        handlers=[handler],
    )


def _run_headless(app: MirrorApp, store: SessionStore, state: SessionState, session_id: str, model: str, max_turns: int) -> int:
    import time as _time

    print(f"Headless mode: {session_id} (model: {model})", flush=True)
    print("Turns will be printed as they happen. Press Ctrl+C to stop.\n", flush=True)
    last_line_count = 0
    try:
        while True:
            jsonl_path = store.path
            if jsonl_path.exists():
                try:
                    lines = jsonl_path.read_text(encoding="utf-8").splitlines()
                    if len(lines) > last_line_count:
                        for line in lines[last_line_count:]:
                            try:
                                event = json.loads(line)
                                if event.get("type") == "turn":
                                    speaker = event.get("speaker", "?").capitalize()
                                    content = event.get("content", "")
                                    import re
                                    content = re.sub(r"```thinking\b[\s\S]*?```", "", content)
                                    content = re.sub(r"<thinking>[\s\S]*?</thinking>", "", content)
                                    print(f"{speaker}: {content.strip()}\n", flush=True)
                            except json.JSONDecodeError:
                                pass
                        last_line_count = len(lines)
                except (OSError, json.JSONDecodeError) as exc:
                    print(f"Error reading JSONL: {exc}", file=sys.stderr)
            try:
                lines = jsonl_path.read_text(encoding="utf-8").splitlines()
                turn_count = sum(1 for line in lines if line.strip() and json.loads(line).get("type") == "turn")
                if max_turns > 0 and turn_count >= max_turns:
                    break
            except (OSError, json.JSONDecodeError):
                pass
            _time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        app.save()
        store.write_markdown(state)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="llm-mirror: two-persona autonomous conversation")
    parser.add_argument("--prompt", type=str, default=None, help="Session seed topic")
    parser.add_argument("--no-seed", action="store_true", default=False, help="Do not use a seed topic")
    parser.add_argument("--scenario", type=str, default="debate", help="Scenario package name (default: debate)")
    parser.add_argument("--free", action="store_true", default=False, help="[deprecated] Use --scenario debate")
    parser.add_argument("--resume", type=str, default=None, help="Resume a session by path or 'latest'")
    parser.add_argument("--model", type=str, default=None, help="Model name")
    parser.add_argument("--session-dir", type=str, default="sessions", help="Directory for session files")
    parser.add_argument("--echo-prompt", type=str, default=None, help="Custom Echo card")
    parser.add_argument("--mirror-prompt", type=str, default=None, help="Custom Mirror card")
    parser.add_argument("--temp", type=float, default=0.8, help="Sampling temperature")
    parser.add_argument("--max-tokens", type=int, default=300, help="Max tokens per turn")
    parser.add_argument("--frequency-penalty", type=float, default=0.0, help="Frequency penalty")
    parser.add_argument("--presence-penalty", type=float, default=0.0, help="Presence penalty")
    parser.add_argument("--max-turns", type=int, default=0, help="Max turns (0=unlimited)")
    parser.add_argument("--log-level", type=str, default="INFO", help="Logging level")
    parser.add_argument("--base-url", type=str, default="http://localhost:8000", help="oMLX base URL")
    parser.add_argument("--thinking", action="store_true", default=False, help="Enable thinking mode")
    parser.add_argument("--headless", action="store_true", default=False, help="Run without TUI (print turns to stdout)")
    parser.add_argument("--turn-delay", type=float, default=3.0, help="Seconds between turns")
    args = parser.parse_args()

    _setup_logging(args.log_level)
    logger = logging.getLogger(__name__)

    if args.resume and args.prompt:
        print("--prompt conflicts with --resume", file=sys.stderr)
        return 2

    try:
        client = OmlxClient(args.base_url)
        health = client.health()
        health_model = health.get("default_model", "")
        models = client.models()
    except OmlxClientError as exc:
        print(f"Is oMLX running on {args.base_url}?", file=sys.stderr)
        logger.error("connection failed: %s", exc)
        return 1

    chosen_model = args.model
    if not chosen_model:
        chosen_model = health_model or (models[0].get("id", "unknown") if models else "unknown")
    logger.info("using model: %s", chosen_model)

    # Build max_model_len from models list or health
    max_model_len = 262144
    for m in models:
        if m.get("id") == chosen_model and m.get("max_model_len"):
            max_model_len = m["max_model_len"]
            break

    session_dir = Path(args.session_dir)
    session_dir.mkdir(parents=True, exist_ok=True)

    # Load packages
    packages = load_packages()
    scenario_name = args.scenario
    if scenario_name not in packages:
        print(f"Unknown scenario: {scenario_name}. Available: {', '.join(packages.keys())}", file=sys.stderr)
        return 2
    package = packages[scenario_name]()

    # Handle --free override for backward compatibility
    if args.free and hasattr(package, "_free"):
        package._free = True

    if args.resume:
        if args.resume == "latest":
            jsonl_files = sorted(session_dir.glob("*.jsonl"))
            if not jsonl_files:
                print("No sessions found to resume.", file=sys.stderr)
                return 1
            session_path = jsonl_files[-1]
        else:
            session_path = Path(args.resume)
        state = load_session(session_path)
        store = SessionStore(session_path)
        logger.info("resumed session: %s", session_path)
        session_id = session_path.stem
    else:
        seed = None
        if args.prompt:
            seed = args.prompt
        elif not args.no_seed:
            seed = random.choice(package.seed_topics)
        meta = SessionMeta(
            model=chosen_model,
            base_url=args.base_url,
            package_name=scenario_name,
            echo_card=args.echo_prompt or package.personas.get("echo", ""),
            mirror_card=args.mirror_prompt or package.personas.get("mirror", ""),
            sampling=Sampling(
                temperature=args.temp,
                max_tokens=args.max_tokens,
                frequency_penalty=args.frequency_penalty,
                presence_penalty=args.presence_penalty,
            ),
            seed=seed,
            max_model_len=max_model_len,
            thinking=args.thinking,
        )
        path = new_session_path(session_dir, seed)
        store = SessionStore(path)
        store.append_event({
            "type": "session",
            "model": meta.model,
            "base_url": meta.base_url,
            "scenario": scenario_name,
            "package_name": meta.package_name,
            "participants": {"echo": {"card": meta.echo_card}, "mirror": {"card": meta.mirror_card}},
            "sampling": {
                "temperature": meta.sampling.temperature,
                "max_tokens": meta.sampling.max_tokens,
                "frequency_penalty": meta.sampling.frequency_penalty,
                "presence_penalty": meta.sampling.presence_penalty,
            },
            "seed": meta.seed,
            "max_model_len": meta.max_model_len,
            "thinking": meta.thinking,
        })
        if seed is not None:
            store.append_event({"type": "injection", "target": "ambient", "content": seed})
        state = SessionState(meta, [], "echo")
        if seed is not None:
            state.messages.append(Message("user", f"Topic: {seed}."))
        store.write_markdown(state)
        logger.info("new session: %s", path)
        session_id = path.stem

    app = MirrorApp(
        client,
        store,
        state,
        package,
        max_turns=args.max_turns,
        turn_delay=args.turn_delay,
    )
    app.start()
    session_id = state.meta.seed or (path.stem if not args.resume else state.meta.package_name)
    if args.headless:
        return _run_headless(app, store, state, session_id, chosen_model, args.max_turns)
    tui = Tui(app, store, session_id, chosen_model)
    try:
        tui.run()
    except Exception as exc:
        logger.exception("tui error")
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    app.save()
    store.write_markdown(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
