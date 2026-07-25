FROM cgr.dev/chainguard/python@sha256:0eddb3213e83cfbd03dd9dbb28d94ced9fa61839f66b29ccb4422bde4b153a2b AS builder

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY src/aiops/requirements.txt .
RUN python -m venv /home/nonroot/venv \
    && /home/nonroot/venv/bin/pip install --no-cache-dir -r requirements.txt

FROM cgr.dev/chainguard/python@sha256:71cda8424b96989702cdfe23d806e059845965e96a1b08da4d39cc0f1cb946a0 AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/home/nonroot/venv/bin:${PATH}"

WORKDIR /app

COPY --from=builder /home/nonroot/venv /home/nonroot/venv
COPY src/aiops/app ./app
COPY src/aiops/runbooks.yaml ./runbooks.yaml

USER 65532:65532
EXPOSE 8080
ENTRYPOINT ["/home/nonroot/venv/bin/python"]
CMD ["-m", "app.main"]
