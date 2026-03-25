"""AI Docker Manager — interactive CLI tool for managing Docker containers and images."""

from __future__ import annotations

import http.client
import re
import socket
import sys
import time
from typing import Any

import docker
from docker.errors import DockerException, NotFound, APIError
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich import box

console = Console()

# ---------------------------------------------------------------------------
# Port / service knowledge base
# ---------------------------------------------------------------------------

# Common port → service name mapping (used for auto-detection labels)
_PORT_SERVICES: dict[int, str] = {
    21: "FTP",
    22: "SSH",
    23: "Telnet",
    25: "SMTP",
    53: "DNS",
    80: "HTTP",
    110: "POP3",
    143: "IMAP",
    443: "HTTPS",
    465: "SMTPS",
    587: "SMTP/TLS",
    993: "IMAPS",
    995: "POP3S",
    1433: "MSSQL",
    1521: "Oracle DB",
    2375: "Docker (unencrypted)",
    2376: "Docker TLS",
    3000: "Web App",
    3306: "MySQL",
    4200: "Angular Dev",
    5000: "Flask / Dev server",
    5432: "PostgreSQL",
    5601: "Kibana",
    5900: "VNC",
    6379: "Redis",
    7474: "Neo4j",
    8080: "HTTP Alt",
    8443: "HTTPS Alt",
    8888: "Jupyter",
    9000: "Web App",
    9200: "Elasticsearch",
    9300: "Elasticsearch cluster",
    11211: "Memcached",
    27017: "MongoDB",
    27018: "MongoDB",
    28017: "MongoDB Web",
}

# Sensitive ports that should trigger a security warning when publicly bound
_SENSITIVE_PORTS: dict[int, str] = {
    22: "SSH — remote shell access exposed",
    23: "Telnet — unencrypted remote shell exposed",
    2375: "Docker daemon (unencrypted!) — full host control possible",
    3306: "MySQL — database port publicly exposed",
    5432: "PostgreSQL — database port publicly exposed",
    5900: "VNC — remote desktop exposed",
    6379: "Redis — no auth by default, data at risk",
    11211: "Memcached — no auth, data-exfiltration risk",
    1433: "MSSQL — database port publicly exposed",
    1521: "Oracle DB — database port publicly exposed",
    27017: "MongoDB — database port publicly exposed",
    9200: "Elasticsearch — data exfiltration risk",
}

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
# Port-scanning helpers
# ---------------------------------------------------------------------------

def _check_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    """Return True if the TCP port is reachable."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _fingerprint_service(host: str, port: int, timeout: float = 2.0) -> str:
    """Try to identify the service running on a port.

    Attempts an HTTP HEAD request first; falls back to a raw banner grab.
    Returns a short descriptive string.
    """
    # 1) HTTP probe
    try:
        conn = http.client.HTTPConnection(host, port, timeout=timeout)
        conn.request("HEAD", "/")
        resp = conn.getresponse()
        parts = [
            resp.getheader("Server", ""),
            resp.getheader("X-Powered-By", ""),
        ]
        info = " / ".join(p for p in parts if p)
        return info if info else f"HTTP {resp.status}"
    except Exception:
        pass

    # 2) Raw banner grab
    try:
        with socket.create_connection((host, port), timeout=timeout) as s:
            s.settimeout(timeout)
            try:
                banner = s.recv(256).decode("utf-8", errors="replace").strip()
                if banner:
                    # Keep only the first line, max 80 chars
                    return banner.splitlines()[0][:80]
            except socket.timeout:
                pass
    except OSError:
        pass

    return _PORT_SERVICES.get(port, "Unknown")


def _resolve_host_ip(raw: str) -> str:
    """Normalise a HostIp value so it is always a connectable address."""
    if raw in ("", "0.0.0.0", "::"):
        return "127.0.0.1"
    return raw


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
# Port Scanner — container → port → service + security alerts
# ---------------------------------------------------------------------------

def scan_container_ports(client: docker.DockerClient, name: str) -> None:
    """Scan all bound ports for a container.

    For each host port:
      - check TCP reachability (green = open, red = closed)
      - fingerprint the service (HTTP header / banner grab)
      - flag sensitive ports with a security warning
    """
    try:
        c = client.containers.get(name)
    except NotFound:
        console.print(f"[red]Container '{name}' not found.[/red]")
        return

    ports = c.ports
    if not ports:
        console.print(f"[yellow]Container '{c.name}' has no bound ports.[/yellow]")
        return

    table = Table(title=f"Port Scan — {c.name}", box=box.ROUNDED, show_lines=True)
    table.add_column("Container Port", style="cyan", no_wrap=True)
    table.add_column("Host Binding", style="bold")
    table.add_column("Status", justify="center")
    table.add_column("Service", style="magenta")
    table.add_column("Fingerprint")
    table.add_column("⚠ Security Alert", style="red")

    with console.status("[cyan]Scanning ports…[/cyan]"):
        for proto_port, bindings in sorted(ports.items()):
            try:
                container_port = int(proto_port.split("/")[0])
            except ValueError:
                container_port = 0

            for binding in bindings or []:
                if not isinstance(binding, dict):
                    continue
                host_ip = _resolve_host_ip(binding.get("HostIp", ""))
                host_port_str = binding.get("HostPort", "")
                if not host_port_str:
                    continue
                try:
                    host_port = int(host_port_str)
                except ValueError:
                    continue

                open_ = _check_port_open(host_ip, host_port)
                status_cell = "[green]● OPEN[/green]" if open_ else "[red]○ CLOSED[/red]"

                service_name = _PORT_SERVICES.get(container_port, _PORT_SERVICES.get(host_port, "Unknown"))

                fingerprint = _fingerprint_service(host_ip, host_port) if open_ else ""

                alert = _SENSITIVE_PORTS.get(container_port) or _SENSITIVE_PORTS.get(host_port, "")

                table.add_row(
                    proto_port,
                    f"{host_ip}:{host_port_str}",
                    status_cell,
                    service_name,
                    fingerprint,
                    f"[bold red]{alert}[/bold red]" if alert else "",
                )

    console.print(table)


# ---------------------------------------------------------------------------
# Live Dashboard — auto-detect all containers + real-time port status
# ---------------------------------------------------------------------------

def _build_dashboard_table(client: docker.DockerClient) -> Table:
    """Build a Rich table showing every container and its port open/closed status."""
    containers = client.containers.list(all=True)

    table = Table(
        title="🖥  Live Container Dashboard",
        box=box.ROUNDED,
        show_lines=True,
    )
    table.add_column("Name", style="bold")
    table.add_column("Image", style="magenta")
    table.add_column("Status", justify="center")
    table.add_column("Container Port", style="cyan")
    table.add_column("Host Binding")
    table.add_column("Open?", justify="center")
    table.add_column("Service", style="blue")
    table.add_column("⚠", style="red")

    for c in containers:
        status_color = "green" if c.status == "running" else "red"
        status_cell = f"[{status_color}]{c.status}[/{status_color}]"
        image_label = c.image.tags[0] if c.image.tags else c.image.short_id

        if not c.ports:
            table.add_row(c.name, image_label, status_cell, "—", "—", "—", "—", "")
            continue

        first = True
        for proto_port, bindings in sorted(c.ports.items()):
            try:
                container_port = int(proto_port.split("/")[0])
            except ValueError:
                container_port = 0

            for binding in bindings or []:
                if not isinstance(binding, dict):
                    continue
                host_ip = _resolve_host_ip(binding.get("HostIp", ""))
                host_port_str = binding.get("HostPort", "")
                if not host_port_str:
                    continue
                try:
                    host_port = int(host_port_str)
                except ValueError:
                    continue

                open_ = _check_port_open(host_ip, host_port, timeout=0.5)
                open_cell = "[green]● OPEN[/green]" if open_ else "[red]○ CLOSED[/red]"
                service = _PORT_SERVICES.get(container_port, "Unknown")
                alert = (
                    "⚠"
                    if container_port in _SENSITIVE_PORTS or host_port in _SENSITIVE_PORTS
                    else ""
                )

                table.add_row(
                    c.name if first else "",
                    image_label if first else "",
                    status_cell if first else "",
                    proto_port,
                    f"{host_ip}:{host_port_str}",
                    open_cell,
                    service,
                    f"[bold red]{alert}[/bold red]",
                )
                first = False

    return table


def live_dashboard(client: docker.DockerClient) -> None:
    """Display a live-updating dashboard of all containers and their port status.

    Refreshes every 5 seconds. Press Ctrl+C to exit.
    """
    console.print("[dim]Live dashboard — refreshes every 5 s. Press Ctrl+C to exit.[/dim]")
    try:
        with Live(console=console, refresh_per_second=0.5) as live:
            while True:
                live.update(_build_dashboard_table(client))
                time.sleep(5)
    except KeyboardInterrupt:
        pass
    console.print("[dim]Dashboard closed.[/dim]")


# ---------------------------------------------------------------------------
# Docker Searcher — find containers by name / image / status
# ---------------------------------------------------------------------------

def docker_searcher(client: docker.DockerClient, query: str) -> None:
    """Search all containers (running + stopped) by name, image tag, status, or ID fragment.

    After displaying matches, offers quick-action shortcuts:
    scan → port-scan a result | start | stop | logs
    """
    query_lower = query.lower().strip()
    if not query_lower:
        console.print("[yellow]Please provide a search term.[/yellow]")
        return

    all_containers = client.containers.list(all=True)
    matched = [
        c for c in all_containers
        if (
            query_lower in c.name.lower()
            or query_lower in c.short_id.lower()
            or any(query_lower in t.lower() for t in (c.image.tags or []))
            or query_lower in c.status.lower()
        )
    ]

    if not matched:
        console.print(f"[yellow]No containers matching '{query}'.[/yellow]")
        return

    table = Table(title=f"Search Results — '{query}'", box=box.ROUNDED, show_lines=True)
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Name", style="bold")
    table.add_column("Image", style="magenta")
    table.add_column("Status")
    table.add_column("Ports")

    for c in matched:
        status_color = "green" if c.status == "running" else "red"
        table.add_row(
            c.short_id,
            c.name,
            c.image.tags[0] if c.image.tags else c.image.short_id,
            f"[{status_color}]{c.status}[/{status_color}]",
            _format_ports(c.ports),
        )

    console.print(table)

    # Quick-action follow-up
    action = console.input(
        "\n[bold]Quick action:[/bold] [dim](s)can ports | (start) | (stop) | (logs) | Enter to skip:[/dim] "
    ).strip().lower()

    if action in {"s", "scan"}:
        target = console.input("[bold]Container name/ID to scan:[/bold] ").strip()
        if target:
            scan_container_ports(client, target)
    elif action == "start":
        target = console.input("[bold]Container name/ID to start:[/bold] ").strip()
        if target:
            start_container(client, target)
    elif action == "stop":
        target = console.input("[bold]Container name/ID to stop:[/bold] ").strip()
        if target:
            stop_container(client, target)
    elif action == "logs":
        target = console.input("[bold]Container name/ID for logs:[/bold] ").strip()
        if target:
            show_logs(client, target)


# ---------------------------------------------------------------------------
# AI Suggest — keyword / pattern based
# ---------------------------------------------------------------------------

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\blist\b.*\bcontainer", re.I), "list_containers"),
    (re.compile(r"\bshow\b.*\bcontainer", re.I), "list_containers"),
    (re.compile(r"\blist\b.*\bimage", re.I), "list_images"),
    (re.compile(r"\bshow\b.*\bimage", re.I), "list_images"),
    (re.compile(r"\bscan\b|\bport.scan\b|\bcheck.port", re.I), "scan_container_ports"),
    (re.compile(r"\bdashboard\b|\blive\s+view\b|\bmonitor\b", re.I), "live_dashboard"),
    (re.compile(r"\bsearch\b|\bfind\b|\bdiscover\b", re.I), "docker_searcher"),
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
            "  • 'show logs for myapp'\n"
            "  • 'scan ports for nginx'\n"
            "  • 'show live dashboard'\n"
            "  • 'find containers with redis'[/yellow]"
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

    elif action == "scan_container_ports":
        if not name:
            name = console.input("[bold]Container name/ID to scan: [/bold]")
        scan_container_ports(client, name)

    elif action == "live_dashboard":
        live_dashboard(client)

    elif action == "docker_searcher":
        query = name or console.input("[bold]Search query: [/bold]")
        docker_searcher(client, query)


# ---------------------------------------------------------------------------
# Interactive menu
# ---------------------------------------------------------------------------

MENU = """
[bold cyan]AI Docker Manager[/bold cyan]
─────────────────────────────────────
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
[bold]12.[/bold] Port Scanner       🔍
[bold]13.[/bold] Live Dashboard     📊
[bold]14.[/bold] Docker Searcher    🔎
 [bold]q.[/bold] Quit
─────────────────────────────────────
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
        elif choice == "12":
            scan_container_ports(client, prompt("Container name/ID to scan"))
        elif choice == "13":
            live_dashboard(client)
        elif choice == "14":
            docker_searcher(client, prompt("Search query (name / image / status)"))
        elif choice in {"q", "quit", "exit"}:
            console.print("[bold]Goodbye![/bold]")
            break
        else:
            console.print("[red]Invalid choice. Please enter a number 1-14 or 'q'.[/red]")


if __name__ == "__main__":
    main()
