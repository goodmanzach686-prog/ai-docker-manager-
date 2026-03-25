"""AI Docker Manager — interactive CLI tool for managing Docker containers and images."""

from __future__ import annotations

import re
import sys
from typing import Any

import docker
from docker.errors import DockerException, NotFound, APIError
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

console = Console()

# ---------------------------------------------------------------------------
# Docker client helpers
# ---------------------------------------------------------------------------

def get_client() -> docker.DockerClient:
    """Return a connected Docker client or exit with a friendly error."""
    try:
        client = docker.from_env()
        client.ping()
        return client
    except DockerException as exc:
        console.print(
            Panel(
                f"[red]Cannot connect to the Docker daemon.[/red]\n{exc}\n\n"
                "Make sure Docker is running and the socket is mounted:\n"
                "  [bold]docker run -it --rm -v /var/run/docker.sock:/var/run/docker.sock ...[/bold]",
                title="Docker Error",
                border_style="red",
            )
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# Action functions
# ---------------------------------------------------------------------------

def _format_ports(ports: dict | None) -> str:
    """Return a human-readable string of exposed ports from a container's port map."""
    if not ports:
        return ""
    parts: list[str] = []
    for proto, bindings in ports.items():
        for binding in bindings or []:
            if isinstance(binding, dict):
                host = f"{binding.get('HostIp', '')}:{binding.get('HostPort', '')}"
            else:
                host = str(binding)
            parts.append(f"{host}/{proto}")
    return ", ".join(parts)


def list_containers(client: docker.DockerClient) -> None:
    """List all containers (running + stopped)."""
    containers = client.containers.list(all=True)
    if not containers:
        console.print("[yellow]No containers found.[/yellow]")
        return

    table = Table(title="Containers", box=box.ROUNDED, show_lines=True)
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Name", style="bold")
    table.add_column("Image", style="magenta")
    table.add_column("Status", style="green")
    table.add_column("Ports")

    for c in containers:
        ports = _format_ports(c.ports)
        status_color = "green" if c.status == "running" else "red"
        table.add_row(
            c.short_id,
            c.name,
            c.image.tags[0] if c.image.tags else c.image.short_id,
            f"[{status_color}]{c.status}[/{status_color}]",
            ports,
        )

    console.print(table)


def list_images(client: docker.DockerClient) -> None:
    """List all locally available images."""
    images = client.images.list()
    if not images:
        console.print("[yellow]No images found.[/yellow]")
        return

    table = Table(title="Images", box=box.ROUNDED, show_lines=True)
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Tags", style="bold")
    table.add_column("Size", justify="right")

    for img in images:
        size_mb = img.attrs.get("Size", 0) / (1024 * 1024)
        table.add_row(
            img.short_id.replace("sha256:", ""),
            "\n".join(img.tags) if img.tags else "<none>",
            f"{size_mb:.1f} MB",
        )

    console.print(table)


def start_container(client: docker.DockerClient, name: str) -> None:
    try:
        c = client.containers.get(name)
        c.start()
        console.print(f"[green]✔ Container '{name}' started.[/green]")
    except NotFound:
        console.print(f"[red]Container '{name}' not found.[/red]")
    except APIError as exc:
        console.print(f"[red]Error starting container: {exc}[/red]")


def stop_container(client: docker.DockerClient, name: str) -> None:
    try:
        c = client.containers.get(name)
        c.stop()
        console.print(f"[yellow]■ Container '{name}' stopped.[/yellow]")
    except NotFound:
        console.print(f"[red]Container '{name}' not found.[/red]")
    except APIError as exc:
        console.print(f"[red]Error stopping container: {exc}[/red]")


def restart_container(client: docker.DockerClient, name: str) -> None:
    try:
        c = client.containers.get(name)
        c.restart()
        console.print(f"[green]↻ Container '{name}' restarted.[/green]")
    except NotFound:
        console.print(f"[red]Container '{name}' not found.[/red]")
    except APIError as exc:
        console.print(f"[red]Error restarting container: {exc}[/red]")


def remove_container(client: docker.DockerClient, name: str) -> None:
    try:
        c = client.containers.get(name)
        c.remove(force=True)
        console.print(f"[red]✖ Container '{name}' removed.[/red]")
    except NotFound:
        console.print(f"[red]Container '{name}' not found.[/red]")
    except APIError as exc:
        console.print(f"[red]Error removing container: {exc}[/red]")


def remove_image(client: docker.DockerClient, name: str) -> None:
    try:
        client.images.remove(name, force=True)
        console.print(f"[red]✖ Image '{name}' removed.[/red]")
    except (NotFound, APIError) as exc:
        console.print(f"[red]Error removing image: {exc}[/red]")


def pull_image(client: docker.DockerClient, name: str) -> None:
    console.print(f"[cyan]Pulling image '{name}'…[/cyan]")
    try:
        image = client.images.pull(name)
        tags = ", ".join(image.tags) if image.tags else image.short_id
        console.print(f"[green]✔ Pulled: {tags}[/green]")
    except APIError as exc:
        console.print(f"[red]Error pulling image: {exc}[/red]")


def run_container(client: docker.DockerClient, image: str, name: str | None = None) -> None:
    console.print(f"[cyan]Running container from image '{image}'…[/cyan]")
    kwargs: dict = {"detach": True}
    if name:
        kwargs["name"] = name
    try:
        c = client.containers.run(image, **kwargs)
        console.print(f"[green]✔ Container started: {c.name} ({c.short_id})[/green]")
    except APIError as exc:
        console.print(f"[red]Error running container: {exc}[/red]")


def show_logs(client: docker.DockerClient, name: str, tail: int = 50) -> None:
    try:
        c = client.containers.get(name)
        logs = c.logs(tail=tail, timestamps=True).decode("utf-8", errors="replace")
        console.print(
            Panel(logs or "[dim]No logs available.[/dim]", title=f"Logs — {name}", border_style="blue")
        )
    except NotFound:
        console.print(f"[red]Container '{name}' not found.[/red]")
    except APIError as exc:
        console.print(f"[red]Error fetching logs: {exc}[/red]")


# ---------------------------------------------------------------------------
# AI Suggest — keyword / pattern based
# ---------------------------------------------------------------------------

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\blist\b.*\bcontainer", re.I), "list_containers"),
    (re.compile(r"\bshow\b.*\bcontainer", re.I), "list_containers"),
    (re.compile(r"\blist\b.*\bimage", re.I), "list_images"),
    (re.compile(r"\bshow\b.*\bimage", re.I), "list_images"),
    (re.compile(r"\bstart\b", re.I), "start_container"),
    (re.compile(r"\bstop\b", re.I), "stop_container"),
    (re.compile(r"\brestart\b", re.I), "restart_container"),
    (re.compile(r"\bremove\b.*\bcontainer|\bdelete\b.*\bcontainer|rm.*container", re.I), "remove_container"),
    (re.compile(r"\bremove\b.*\bimage|\bdelete\b.*\bimage|rm.*image", re.I), "remove_image"),
    (re.compile(r"\bpull\b", re.I), "pull_image"),
    (re.compile(r"\brun\b", re.I), "run_container"),
    (re.compile(r"\blog", re.I), "show_logs"),
]

_NAME_PATTERN = re.compile(
    r"\b([\w./-]+(?::[\w.-]+)?)\s*(?:container|image|log)?\s*$", re.I
)


def _extract_name(text: str) -> str | None:
    """Try to extract a container/image name from the user's text."""
    # Remove common filler words
    cleaned = re.sub(
        r"\b(my|the|a|an|please|can you|could you|i want to|i need to)\b",
        "",
        text,
        flags=re.I,
    ).strip()
    m = _NAME_PATTERN.search(cleaned)
    if m:
        candidate = m.group(1)
        # Ignore generic words
        if candidate.lower() not in {
            "container", "image", "log", "logs", "running", "all",
            "list", "show", "stop", "start", "restart", "remove", "delete", "pull", "run",
        }:
            return candidate
    return None


def ai_suggest(client: docker.DockerClient, request: str) -> None:
    """Parse a plain-English request and execute the matching Docker action."""
    console.print(f"[bold cyan]AI processing:[/bold cyan] {request!r}")

    action: str | None = None
    for pattern, act in _PATTERNS:
        if pattern.search(request):
            action = act
            break

    if action is None:
        console.print(
            "[yellow]I couldn't understand that request. Try something like:\n"
            "  • 'list containers'\n"
            "  • 'stop my nginx container'\n"
            "  • 'pull ubuntu:22.04'\n"
            "  • 'show logs for myapp'[/yellow]"
        )
        return

    name = _extract_name(request)

    # Map action names to callables — avoids dynamic globals() lookup.
    _container_actions: dict[str, Any] = {
        "start_container": start_container,
        "stop_container": stop_container,
        "restart_container": restart_container,
        "remove_container": remove_container,
        "show_logs": show_logs,
    }

    if action in _container_actions:
        if not name:
            name = console.input(f"[bold]Container name/ID for [cyan]{action}[/cyan]: [/bold]")
        _container_actions[action](client, name)

    elif action == "remove_image":
        if not name:
            name = console.input("[bold]Image name/ID to remove: [/bold]")
        remove_image(client, name)

    elif action == "pull_image":
        if not name:
            name = console.input("[bold]Image to pull (e.g. ubuntu:22.04): [/bold]")
        pull_image(client, name)

    elif action == "run_container":
        if not name:
            name = console.input("[bold]Image to run: [/bold]")
        run_container(client, name)

    elif action == "list_containers":
        list_containers(client)

    elif action == "list_images":
        list_images(client)


# ---------------------------------------------------------------------------
# Interactive menu
# ---------------------------------------------------------------------------

MENU = """
[bold cyan]AI Docker Manager[/bold cyan]
─────────────────────────────────
 [bold]1.[/bold] List containers
 [bold]2.[/bold] List images
 [bold]3.[/bold] Start container
 [bold]4.[/bold] Stop container
 [bold]5.[/bold] Restart container
 [bold]6.[/bold] Pull image
 [bold]7.[/bold] Run container from image
 [bold]8.[/bold] Show container logs
 [bold]9.[/bold] Remove container
[bold]10.[/bold] Remove image
[bold]11.[/bold] AI Suggest (plain English)
 [bold]q.[/bold] Quit
─────────────────────────────────
"""


def prompt(label: str) -> str:
    return console.input(f"[bold]{label}:[/bold] ").strip()


def main() -> None:
    client = get_client()
    console.print(
        Panel(
            "[bold green]Connected to Docker daemon[/bold green]",
            title="AI Docker Manager",
            border_style="green",
        )
    )

    while True:
        console.print(MENU)
        choice = console.input("[bold]Choice:[/bold] ").strip().lower()

        if choice == "1":
            list_containers(client)
        elif choice == "2":
            list_images(client)
        elif choice == "3":
            start_container(client, prompt("Container name/ID"))
        elif choice == "4":
            stop_container(client, prompt("Container name/ID"))
        elif choice == "5":
            restart_container(client, prompt("Container name/ID"))
        elif choice == "6":
            pull_image(client, prompt("Image name (e.g. ubuntu:22.04)"))
        elif choice == "7":
            image = prompt("Image name")
            cname = prompt("Container name (leave blank for auto)")
            run_container(client, image, name=cname or None)
        elif choice == "8":
            show_logs(client, prompt("Container name/ID"))
        elif choice == "9":
            remove_container(client, prompt("Container name/ID"))
        elif choice == "10":
            remove_image(client, prompt("Image name/ID"))
        elif choice == "11":
            ai_suggest(client, prompt("Describe what you want to do"))
        elif choice in {"q", "quit", "exit"}:
            console.print("[bold]Goodbye![/bold]")
            break
        else:
            console.print("[red]Invalid choice. Please enter a number 1–11 or 'q'.[/red]")


if __name__ == "__main__":
    main()
