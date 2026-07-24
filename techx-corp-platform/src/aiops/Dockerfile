FROM cgr.dev/chainguard/python@sha256:967409cf4148210d7c1bb872ffdda42a8b73cfc738f95eae7413045d0d6c30ee AS builder

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY src/aiops/requirements.txt .
RUN python -m venv /home/nonroot/venv \
    && /home/nonroot/venv/bin/pip install --no-cache-dir -r requirements.txt

FROM cgr.dev/chainguard/python@sha256:2c6a2e8bdeb1336cd8545d3586d1c1e5b4f7564ef00924b0447ebfbe57a549ee AS runtime

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
