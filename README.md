# AI Docker Manager

[![Build and Push Docker Image](https://github.com/goodmanzach686-prog/ai-docker-manager-/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/goodmanzach686-prog/ai-docker-manager-/actions/workflows/docker-publish.yml)

An **AI-assisted Docker manager** — a rich interactive CLI that lets you list, start, stop, run, inspect, and remove containers and images using simple menus or plain-English commands.

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

- 📋 **List containers** — running + stopped, with status colours
- 🖼️ **List images** — ID, tags, and size
- ▶️ **Start / Stop / Restart** a container by name or ID
- 📥 **Pull** any Docker Hub image
- 🚀 **Run** a new container from an image
- 📜 **Show logs** — last 50 lines with timestamps
- 🗑️ **Remove** a container or image
- 🤖 **AI Suggest** — describe what you want in plain English (no API keys required)
  - `"stop my nginx container"` → stops the nginx container
  - `"pull ubuntu:22.04"` → pulls the image
  - `"show logs for myapp"` → prints the last 50 lines

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
        └── docker-publish.yml      # CI: build & push to GHCR
```
