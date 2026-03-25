FROM python:3.12-slim

LABEL org.opencontainers.image.source="https://github.com/goodmanzach686-prog/ai-docker-manager-"
LABEL org.opencontainers.image.description="AI-assisted Docker manager CLI"
LABEL org.opencontainers.image.licenses="MIT"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

# The Docker socket must be mounted at runtime so the app can talk to the host daemon:
#   docker run -it --rm -v /var/run/docker.sock:/var/run/docker.sock <image>
CMD ["python", "app.py"]
