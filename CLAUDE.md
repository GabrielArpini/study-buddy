# study-buddy — CLAUDE.md

Socratic CLI study companion. Two modes: **concept** (Socratic tutor — asks questions, never lectures) and **project** (dev journal scribe — captures narrative entries and maintains a typed moment graph while the user thinks out loud while building).

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
  tools.py        # Tool schemas (TOOLS, PROJECT_TOOLS) + ToolExecutor
  renderer.py     # Rich display for !commands + PDF extraction
  git_ops.py      # Vault git init + session commit
  models.py       # Pydantic models: Message, Tool, ToolCall, Response
  connectors/
    base.py       # LLMConnector ABC
    anthropic.py  # Anthropic connector
    openai.py     # OpenAI connector
    ollama.py     # Ollama connector
```

## Topic modes

| Mode | Purpose | LLM role |
|---|---|---|
| **concept** | Study a subject — recall, explanation, synthesis | Socratic tutor: ask, never lecture |
| **project** | Build something — journal progress as it happens | Scribe: capture, never evaluate |

Topic type is read from YAML frontmatter (`type: project`); absent = concept.

### Concept mode vault sections
`Sources | Core Concepts | Understanding (Solid/Shaky/Not Yet Engaged) | My Synthesis | Session Log`

### Project mode vault sections
`Goal | Timeline | Breakthroughs | Blockers | Decisions | Sources | Graph (Nodes/Edges) | Session Log`

- **Timeline** — every `record_moment` call writes a dated `### YYYY-MM-DD [type]` entry here
- **Breakthroughs / Blockers** — curated bullet lists auto-populated from matching moment types
- **Graph** — typed nodes (`milestone | uncertainty | certainty | blocker`) with directed edges (`resolves`, `contributes`); rendered by `!graph` and queryable by `!recall`
- **Decisions** — explicit mutually-exclusive choices, via `record_decision()`

## Request flow

```
user types + presses Enter
  → repl.py: run_repl()
    → session.py: StudySession.send()
      → if "!recall <query>": session.py: _run_recall() [fresh single-turn, no history mutation]
      → if other "!" prefix: renderer.py: handle_command() [local, no LLM]
      → else:
          (project mode only) session.py: _classify_moment()
            → single focused LLM call → hint word (progress/breakthrough/blocker/...)
            → hint appended to user message as "[moment-type: X]"
          _run_tool_loop()
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
  topics/<topic>.md        concept: Sources | Core Concepts | Understanding
                             (Solid/Shaky/Not Yet Engaged) | My Synthesis | Session Log
                           project: Goal | Timeline | Breakthroughs | Blockers |
                             Decisions | Sources | Graph (Nodes/Edges) | Session Log
  _daily/YYYY-MM-DD.md     daily activity log
```

Topic notes use YAML frontmatter (`topic`, `created`, `last_session`, optionally `type: project`). All vault mutations go through `vault.py` — never write topic files directly.

## Adding a new LLM connector

1. Create `study/connectors/<name>.py` implementing `LLMConnector` (`complete` + `stream`)
2. Register it in `study/connectors/__init__.py: get_connector()`
3. Add the name to the `questionary.select` choices in `cli.py: cmd_config()`

## Adding a new tool

**Concept mode:**
1. Add a `Tool(...)` entry to `TOOLS` in `tools.py`
2. Add a `_tool_<name>` method on `ToolExecutor`
3. Add the underlying vault operation to `vault.py` if needed

**Project mode:**
1. Add a `Tool(...)` entry to `PROJECT_TOOLS` in `tools.py`
   — use `_get_tool(TOOLS, "name")` to reuse shared tool schemas instead of duplicating
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
!graph                        # concept graph tree (or typed project graph in project mode)
!timeline                     # last 30 daily logs
!topics                       # all topics + last session dates
!add path/to/file.pdf         # inject PDF text into next message
!recall <query>               # narrative recall query against current project journal
```
