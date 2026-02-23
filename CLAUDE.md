# study-buddy — CLAUDE.md

Socratic CLI study companion. The LLM acts as a tutor that asks questions, never lectures. It reads/writes a local markdown vault to track learner understanding over time.

## Stack

- **Python 3.12+**, managed with `uv`
- **Click** — CLI entrypoint
- **prompt_toolkit** — REPL (Enter = submit, Shift+Enter = newline)
- **Rich** — terminal rendering (tables, trees, panels)
- **Pydantic** — data models (`Message`, `Tool`, `Response`)
- **GitPython** — auto-commit vault after each session
- **pdfplumber** — optional PDF ingestion

## Project layout

```
study/
  cli.py          # Click entrypoint — topic picker, config wizard
  config.py       # ~/.study/config.toml (connector, model, vault path)
  session.py      # StudySession — system prompt assembly, agentic tool loop
  repl.py         # prompt_toolkit REPL
  vault.py        # All vault read/write operations
  tools.py        # Tool schemas + ToolExecutor (dispatches LLM tool calls)
  renderer.py     # Rich display for !commands + PDF extraction
  git_ops.py      # Vault git init + session commit
  models.py       # Pydantic models: Message, Tool, ToolCall, Response
  connectors/
    base.py       # LLMConnector ABC
    anthropic.py  # Anthropic connector
    openai.py     # OpenAI connector
    ollama.py     # Ollama connector
```

## Request flow

```
user types + presses Enter
  → repl.py: run_repl()
    → session.py: StudySession.send()
      → if "!" prefix: renderer.py: handle_command() [local, no LLM]
      → else: _run_tool_loop()
        → connector.complete(messages, tools)
        → if tool_calls: tools.py: ToolExecutor.execute()
          → vault.py: mutate vault
        → loop up to 10 rounds until stop_reason == "stop"
        → return final assistant text
  → repl.py: print reply
```

## Vault structure

```
~/Documents/study-vault/   (configurable)
  _framework.md            system prompt instructions for the LLM
  _profile.md              learner profile (LLM-maintained)
  topics/<topic>.md        one file per topic, fixed sections:
                             Sources | Core Concepts | Understanding
                             (Solid/Shaky/Not Yet Engaged) |
                             My Synthesis | Session Log
  _daily/YYYY-MM-DD.md     daily activity log
```

Topic notes use YAML frontmatter (`topic`, `created`, `last_session`). All vault mutations go through `vault.py` — never write topic files directly.

## Adding a new LLM connector

1. Create `study/connectors/<name>.py` implementing `LLMConnector` (`complete` + `stream`)
2. Register it in `study/connectors/__init__.py: get_connector()`
3. Add the name to the `questionary.select` choices in `cli.py: cmd_config()`

## Adding a new tool

1. Add a `Tool(...)` entry to `TOOLS` in `tools.py`
2. Add a `_tool_<name>` method on `ToolExecutor`
3. Add the underlying vault operation to `vault.py` if needed

## Config

Stored at `~/.study/config.toml`. Defaults:

```toml
[llm]
connector = "ollama"
model = "qwen2.5:7b"

[vault]
path = "~/Documents/study-vault"
```

Run `study config` to change interactively.

## Common commands

```bash
uv run study                  # start (topic picker)
uv run study --topic foo      # start on specific topic
uv run study ls               # list topics
uv run study config           # reconfigure

# Inside the REPL
!status                       # understanding table for current topic
!graph                        # concept graph tree
!timeline                     # last 30 daily logs
!topics                       # all topics + last session dates
!add path/to/file.pdf         # inject PDF text into next message
```
