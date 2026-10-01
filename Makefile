.PHONY: sync test lint help run run-free resume headless

sync:
	uv sync

test:
	uv run pytest

lint:
	uv run ruff check .

help:
	uv run llm-mirror --help

run:
	uv run llm-mirror

run-free:
	uv run llm-mirror --free

resume:
	uv run llm-mirror --resume latest

headless:
	uv run llm-mirror --headless --turn-delay 3.0

headless-free:
	uv run llm-mirror --headless --turn-delay 3.0 --no-seed --free

headless-thinking:
	uv run llm-mirror --headless --turn-delay 1.0 --thinking
