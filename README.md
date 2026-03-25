# AI Docker Manager

[![Build and Push Docker Image](https://github.com/goodmanzach686-prog/ai-docker-manager-/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/goodmanzach686-prog/ai-docker-manager-/actions/workflows/docker-publish.yml)

An **AI-assisted Docker manager** — a rich interactive CLI that lets you list, start, stop, run, inspect, and remove containers and images, **scan ports**, view a **live dashboard**, **fingerprint services**, and receive **security alerts** — all from plain-English commands or a numbered menu.

---

## Quick Start

Pull the pre-built image from GitHub Container Registry and run it:

```bash
docker pull ghcr.io/goodmanzach686-prog/ai-docker-manager-:latest
docker run -it --rm -v /var/run/docker.sock:/var/run/docker.sock ghcr.io/goodmanzach686-prog/ai-docker-manager-:latest
```

> **Important:** the `-v /var/run/docker.sock:/var/run/docker.sock` flag mounts your host Docker socket so the manager can control your local containers.

---

## Features

### Container & Image Management
- 📋 **List containers** — running + stopped, with status colours
- 🖼️ **List images** — ID, tags, and size
- ▶️ **Start / Stop / Restart** a container by name or ID
- 📥 **Pull** any Docker Hub image
- 🚀 **Run** a new container from an image
- 📜 **Show logs** — last 50 lines with timestamps
- 🗑️ **Remove** a container or image

### Port Scanner 🔍
- **Auto-detect containers** → map each container to its bound ports and services
- **TCP reachability check** — 🟢 green = open, 🔴 red = closed
- **Service fingerprinting** — identifies services by HTTP response headers (`Server`, `X-Powered-By`) or raw TCP banner grabs
- **Security alerts** — warns when sensitive ports are publicly exposed (SSH, databases, Redis, Elasticsearch, Docker daemon, etc.)

### Live Dashboard 📊
- Auto-detects **all** containers (running + stopped)
- Shows every container → port → open/closed status in a live-refreshing table
- Highlights ⚠ security-sensitive ports at a glance
- Refreshes every 5 seconds — press `Ctrl+C` to exit

### Docker Searcher 🔎
- Search containers by **name**, **image tag**, **status**, or **ID fragment**
- One-click follow-up actions from search results:
  - Scan ports, start, stop, or view logs — all without leaving the searcher

### AI Suggest 🤖
Describe what you want in plain English — no API keys required:

| You type | What happens |
|---|---|
| `"stop my nginx container"` | Stops the nginx container |
| `"pull ubuntu:22.04"` | Pulls the image |
| `"show logs for myapp"` | Prints the last 50 lines |
| `"scan ports for myapp"` | Runs the port scanner on myapp |
| `"show live dashboard"` | Opens the live dashboard |
| `"find containers with redis"` | Searches for redis containers |

---

## Security Alerts

The port scanner and live dashboard automatically flag the following sensitive ports when they are bound to a host interface:

| Port | Service | Risk |
|------|---------|------|
| 22 | SSH | Remote shell exposed |
| 23 | Telnet | Unencrypted remote shell |
| 2375 | Docker daemon | Full host control possible |
| 3306 | MySQL | Database exposed |
| 5432 | PostgreSQL | Database exposed |
| 5900 | VNC | Remote desktop exposed |
| 6379 | Redis | No auth by default |
| 9200 | Elasticsearch | Data exfiltration risk |
| 11211 | Memcached | No auth, data at risk |
| 27017 | MongoDB | Database exposed |

---

## Requirements

- **Docker** installed and running on the host machine
- The Docker socket mounted when running the container (see Quick Start)

---

## Build Locally

```bash
git clone https://github.com/goodmanzach686-prog/ai-docker-manager-.git
cd ai-docker-manager-
docker build -t ai-docker-manager .
docker run -it --rm -v /var/run/docker.sock:/var/run/docker.sock ai-docker-manager
```

Or run directly with Python (requires Python 3.12+):

```bash
pip install -r requirements.txt
python app.py
```

---

## Project Structure

```
.
├── app.py                          # Main CLI application
├── requirements.txt                # Python dependencies
├── Dockerfile                      # Container build definition
└── .github/
    └── workflows/
        └── docker-publish.yml      # CI: build & push to GHCR on every push to main
```

