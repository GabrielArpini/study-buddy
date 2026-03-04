from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

import study.vault as vault_mod

console = Console()


def handle_command(command: str, vault: Path, topic: str) -> bool:
    """
    Dispatch a ! command. Returns True if handled, False if unknown.
    All rendering is local — no API calls.
    """
    parts = command.strip().split(None, 1)
    cmd = parts[0].lstrip("!").lower()
    arg = parts[1] if len(parts) > 1 else ""

    if cmd == "status":
        render_status(vault, arg.strip() or topic)
    elif cmd == "timeline":
        render_timeline(vault)
    elif cmd == "graph":
        if vault_mod.topic_type(vault, topic) == "project":
            render_project_graph(vault, topic)
        else:
            render_graph(vault, topic)
    elif cmd == "topics":
        render_topics(vault)
    elif cmd == "help":
        render_help()
    elif cmd == "add":
        if not arg:
            console.print("[red]Usage: !add path/to/file.pdf[/red]")
            return True
        return False  # signal caller to handle PDF injection
    else:
        console.print(f"[red]Unknown command: {command}[/red]")
    return True


def render_status(vault: Path, topic: str) -> None:
    """Show understanding levels as a Rich table."""
    path = vault_mod.topic_path(vault, topic)
    if not path.exists():
        console.print(f"[yellow]No note found for topic '{topic}'[/yellow]")
        return

    content = path.read_text()

    table = Table(title=f"Understanding: {topic}", show_lines=True)
    table.add_column("Solid", style="green", min_width=20)
    table.add_column("Shaky", style="yellow", min_width=20)
    table.add_column("Not Yet Engaged", style="red", min_width=20)

    solid = _extract_bullets(vault_mod.get_section(content, "Understanding/Solid"))
    shaky = _extract_bullets(vault_mod.get_section(content, "Understanding/Shaky"))
    not_yet = _extract_bullets(vault_mod.get_section(content, "Understanding/Not Yet Engaged"))

    max_rows = max(len(solid), len(shaky), len(not_yet), 1)
    for i in range(max_rows):
        table.add_row(
            solid[i] if i < len(solid) else "",
            shaky[i] if i < len(shaky) else "",
            not_yet[i] if i < len(not_yet) else "",
        )

    console.print(table)


def render_timeline(vault: Path) -> None:
    """Show daily log entries as a Rich table."""
    daily_dir = vault / "_daily"
    table = Table(title="Study Timeline", show_lines=True)
    table.add_column("Date", style="cyan", min_width=12)
    table.add_column("Activity")

    if not daily_dir.exists():
        console.print("[yellow]No daily logs found.[/yellow]")
        return

    log_files = sorted(daily_dir.glob("*.md"), reverse=True)
    if not log_files:
        console.print("[yellow]No daily logs found.[/yellow]")
        return

    for log_file in log_files[:30]:  # last 30 days
        day = log_file.stem
        content = log_file.read_text()
        # Extract bullet lines
        bullets = [l.lstrip("- ").strip() for l in content.splitlines() if l.startswith("- ")]
        activity = "\n".join(bullets) if bullets else "(empty)"
        table.add_row(day, activity)

    console.print(table)


def render_graph(vault: Path, current_topic: str) -> None:
    """Show concept graph as a Rich Tree."""
    topics = vault_mod.list_topics(vault)
    if not topics:
        console.print("[yellow]No topics in vault yet.[/yellow]")
        return

    tree = Tree(f"[bold cyan]Vault Graph[/bold cyan]")
    for topic in topics:
        wikilinks = vault_mod.get_all_wikilinks(vault, topic)
        marker = "●" if topic == current_topic else " "
        label = f"[bold]{marker} {escape(topic)}[/bold]" if topic == current_topic else f"{marker} {escape(topic)}"
        branch = tree.add(label)

        concepts = wikilinks.get("concepts", [])
        cross = wikilinks.get("cross_topic", [])

        if concepts:
            concept_node = branch.add("[dim]concepts[/dim]")
            for c in concepts[:8]:
                concept_node.add(f"[dim]{escape(c)}[/dim]")
            if len(concepts) > 8:
                concept_node.add(f"[dim]... +{len(concepts)-8} more[/dim]")

        if cross:
            for ct in cross:
                obs_link = f"obsidian://open?vault=study-vault&file=topics/{escape(ct)}"
                branch.add(f"[blue]→ {escape(ct)}[/blue]  [dim]{obs_link}[/dim]")

    console.print(Panel(tree, title="Concept Graph", border_style="cyan"))


def render_topics(vault: Path) -> None:
    """List topics with last-session dates as a nested tree."""
    topics = vault_mod.list_topics(vault)
    if not topics:
        console.print("[yellow]No topics yet. Start a session with: study --topic <name>[/yellow]")
        return

    tree = Tree("[bold]Topics[/bold]")
    nodes: dict[str, Tree] = {}

    for topic in topics:
        last = vault_mod.get_last_session(vault, topic) or "—"
        parts = topic.split("/")
        name = parts[-1]
        label = f"[cyan]{escape(name)}[/cyan]  [dim]{last}[/dim]"

        parent_key = "/".join(parts[:-1])
        parent_node = nodes.get(parent_key, tree)
        nodes[topic] = parent_node.add(label)

    console.print(Panel(tree, title="Topics", border_style="cyan"))


def render_help() -> None:
    """Show a panel listing all REPL commands."""
    lines = [
        "[bold]!status[/bold]              understanding table for current topic",
        "[bold]!graph[/bold]               concept graph tree (or project graph in project mode)",
        "[bold]!timeline[/bold]            last 30 daily logs",
        "[bold]!topics[/bold]              all topics + last session dates",
        "[bold]!add <path>[/bold]          inject PDF text into next message",
        "[bold]!recall <query>[/bold]      ask a narrative question about this project",
        "[bold]!help[/bold]                show this help",
        "",
        "[bold]/exit[/bold]          end session",
        "[bold]Shift+Enter[/bold]    newline without submitting",
    ]
    console.print(Panel("\n".join(lines), title="commands", border_style="dim"))


def render_graph_snapshot(vault: Path, topic: str) -> None:
    """Render a compact status panel on REPL boot."""
    path = vault_mod.topic_path(vault, topic)

    lines = []
    if path.exists():
        content = path.read_text()
        solid = _extract_bullets(vault_mod.get_section(content, "Understanding/Solid"))
        shaky = _extract_bullets(vault_mod.get_section(content, "Understanding/Shaky"))
        not_yet = _extract_bullets(vault_mod.get_section(content, "Understanding/Not Yet Engaged"))

        if solid:
            lines.append(f"[green]Solid ({len(solid)}):[/green] " + ", ".join(escape(c) for c in solid[:3]))
        if shaky:
            lines.append(f"[yellow]Shaky ({len(shaky)}):[/yellow] " + ", ".join(escape(c) for c in shaky[:3]))
        if not_yet:
            lines.append(f"[red]Not Yet ({len(not_yet)}):[/red] " + ", ".join(escape(c) for c in not_yet[:3]))

        wikilinks = vault_mod.get_all_wikilinks(vault, topic)
        cross = wikilinks.get("cross_topic", [])
        if cross:
            lines.append(f"[blue]Linked topics:[/blue] " + ", ".join(escape(ct) for ct in cross))

    if not lines:
        lines.append("[dim]No notes yet — let's build them together.[/dim]")

    console.print(Panel("\n".join(lines), title=f"[bold]{escape(topic)}[/bold]", border_style="cyan"))


def render_session_summary(summary: dict) -> None:
    """Render a session summary panel before exit."""
    lines = [
        f"topic: [bold]{summary['topic']}[/bold]   duration: [bold]{summary['duration']}[/bold]",
        "",
        f"[bold]{summary['exchanges']}[/bold] exchange(s) · [bold]{summary['words']}[/bold] word(s) written",
    ]

    stats = summary.get("stats", {})
    vault_lines = []

    concepts_added = stats.get("concepts_added", 0)
    if concepts_added:
        vault_lines.append(f"  [green]+[/green] {concepts_added} concept(s) added")

    understanding_updates = stats.get("understanding_updates", [])
    if understanding_updates:
        solid = [c for c, lvl in understanding_updates if lvl == "Solid"]
        shaky = [c for c, lvl in understanding_updates if lvl == "Shaky"]
        not_yet = [c for c, lvl in understanding_updates if lvl == "Not Yet Engaged"]
        parts = []
        if solid:
            parts.append(f"[green]{len(solid)} → Solid[/green]")
        if shaky:
            parts.append(f"[yellow]{len(shaky)} → Shaky[/yellow]")
        if not_yet:
            parts.append(f"[red]{len(not_yet)} → Not Yet[/red]")
        vault_lines.append("  [cyan]↑[/cyan] " + "  [dim]~[/dim] ".join(parts))

    sources_added = stats.get("sources_added", 0)
    if sources_added:
        vault_lines.append(f"  [magenta]◉[/magenta] {sources_added} source(s) added")

    subtopics_created = stats.get("subtopics_created", [])
    for sub in subtopics_created:
        vault_lines.append(f"  [cyan]◆[/cyan] subtopic: {sub}")

    moments_recorded = stats.get("moments_recorded", 0)
    if moments_recorded:
        vault_lines.append(f"  [cyan]◎[/cyan] {moments_recorded} moment(s) captured")

    breakthroughs = stats.get("breakthroughs", [])
    if breakthroughs:
        vault_lines.append(f"  [green]★[/green] {len(breakthroughs)} breakthrough(s)")

    blockers_logged = stats.get("blockers_logged", [])
    if blockers_logged:
        vault_lines.append(f"  [yellow]⚠[/yellow] {len(blockers_logged)} blocker(s) logged")

    graph_nodes_added = stats.get("graph_nodes_added", 0)
    if graph_nodes_added:
        vault_lines.append(f"  [magenta]◈[/magenta] {graph_nodes_added} graph node(s)")

    if vault_lines:
        lines.append("")
        lines.append("vault")
        lines.extend(vault_lines)

    console.print(Panel("\n".join(lines), title="[bold]session summary[/bold]", border_style="dim"))


def render_project_graph(vault: Path, topic: str) -> None:
    """Render the typed project graph as a Rich Tree."""
    nodes_text = vault_mod.get_graph_nodes(vault, topic)
    edges_text = vault_mod.get_graph_edges(vault, topic)

    if not nodes_text.strip():
        console.print("[yellow]No graph nodes yet.[/yellow]")
        return

    node_pattern = re.compile(r'- \[(\w+)\] ([\w-]+): "([^"]+)" \(([^)]+)\)')
    nodes = [
        {"type": m.group(1), "slug": m.group(2), "text": m.group(3), "date": m.group(4)}
        for m in node_pattern.finditer(nodes_text)
    ]

    edge_pattern = re.compile(r'- ([\w-]+) → (\w+) → ([\w-]+)')
    edges = [
        {"from": m.group(1), "edge": m.group(2), "to": m.group(3)}
        for m in edge_pattern.finditer(edges_text)
    ]

    outgoing: dict[str, list[str]] = {}
    for edge in edges:
        outgoing.setdefault(edge["from"], []).append(
            f"[dim]→ {edge['edge']} →[/dim] {edge['to']}"
        )

    type_colors = {
        "milestone": "bold green",
        "certainty": "green",
        "uncertainty": "yellow",
        "blocker": "red",
    }
    tree = Tree(f"[bold cyan]{escape(topic)} — graph[/bold cyan]")
    for node_type in ("milestone", "certainty", "uncertainty", "blocker"):
        type_nodes = [n for n in nodes if n["type"] == node_type]
        if not type_nodes:
            continue
        color = type_colors.get(node_type, "white")
        branch = tree.add(f"[{color}]{node_type}[/{color}]")
        for node in type_nodes:
            node_branch = branch.add(
                f"[dim]{node['date']}[/dim]  [{color}]{escape(node['slug'])}[/{color}]: {escape(node['text'])}"
            )
            for edge_label in outgoing.get(node["slug"], []):
                node_branch.add(edge_label)

    console.print(Panel(tree, title="Project Graph", border_style="cyan"))


def extract_pdf_text(pdf_path: str) -> str:
    """Extract text from a PDF file using pdfplumber."""
    try:
        import pdfplumber
        path = Path(pdf_path).expanduser()
        if not path.exists():
            return f"Error: file not found: {pdf_path}"
        texts = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    texts.append(text)
        if not texts:
            return "Error: could not extract text from PDF (possibly image-only)."
        return "\n\n".join(texts)
    except ImportError:
        return "Error: pdfplumber not installed."
    except Exception as e:
        return f"Error reading PDF: {e}"


def _extract_bullets(section_content: str) -> list[str]:
    """Extract bullet items from a section, stripping wikilink brackets."""
    bullets = []
    for line in section_content.splitlines():
        line = line.strip()
        if line.startswith("- "):
            # Strip wikilink syntax [[...]]
            item = re.sub(r"\[\[([^\]]+)\]\]", r"\1", line[2:])
            # Strip notes after em-dash
            item = item.split(" — ")[0].strip()
            bullets.append(item)
    return bullets
