from __future__ import annotations

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings
from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape

from study.renderer import render_session_summary
from study.session import StudySession

console = Console()


def _make_toolbar(topic: str, model: str) -> HTML:
    return HTML(
        f"<b>[topic: {topic}]</b>  <i>[{model}]</i>  "
        "<dim>Enter to send | Shift+Enter for newline | /exit to quit | !help for commands</dim>"
    )


def run_repl(session: StudySession, model_label: str) -> None:
    """
    Run the interactive prompt_toolkit REPL.
    Enter = submit, Shift+Enter = newline (via Ghostty ESC+CR mapping).
    """
    recap = session.boot()

    kb = KeyBindings()

    # Enter submits (eager so it overrides the multiline default)
    @kb.add("enter", eager=True)
    def _submit(event):
        event.current_buffer.validate_and_handle()

    # Shift+Enter inserts a newline (Ghostty maps shift+enter to ESC+CR)
    @kb.add("escape", "enter")
    def _newline(event):
        event.current_buffer.insert_text("\n")

    prompt_session: PromptSession = PromptSession(
        multiline=True,
        key_bindings=kb,
        bottom_toolbar=lambda: _make_toolbar(session.topic, model_label),
        prompt_continuation="  ",
    )

    console.print(
        f"[bold cyan]study-buddy[/bold cyan] — topic: [bold]{escape(session.topic)}[/bold]\n"
        "[dim]Enter to send, Shift+Enter for newline, /exit or Ctrl+D to quit[/dim]\n"
    )

    if recap:
        console.print("[bold]Assistant:[/bold]")
        console.print(Markdown(recap))
        console.print()

    while True:
        try:
            text = prompt_session.prompt("> ")
        except KeyboardInterrupt:
            continue
        except EOFError:
            # Ctrl+D
            _do_exit(session)
            break

        text = text.strip()
        if not text:
            continue

        if text.lower() in ("/exit", "/quit"):
            _do_exit(session)
            break

        try:
            reply = session.send(text)
            if reply:
                console.print("\n[bold]Assistant:[/bold]")
                console.print(Markdown(reply))
                console.print()
        except Exception as e:
            console.print(f"[red]Error: {escape(str(e))}[/red]")


def _do_exit(session: StudySession) -> None:
    console.print("\n[dim]Ending session...[/dim]")
    try:
        session.end_session()
    except Exception as e:
        console.print(f"[yellow]Warning: could not finalize session: {e}[/yellow]")
    render_session_summary(session.get_summary())
    console.print("[bold cyan]Goodbye![/bold cyan]")
