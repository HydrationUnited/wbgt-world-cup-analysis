ARG DEFAULT_PYTHON=3.11

FROM ghcr.io/astral-sh/uv:python${DEFAULT_PYTHON}-trixie-slim AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends git
WORKDIR /usr/local/WCHA
COPY . .
RUN uv pip install --system -e ".[dev]"
USER 1000:1000
CMD ["pytest", "-v", "tests/"]
