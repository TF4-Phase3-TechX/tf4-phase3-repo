FROM python:3.12-slim-bookworm@sha256:d50fb7611f86d04a3b0471b46d7557818d88983fc3136726336b2a4c657aa30b AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY src/aiops/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/aiops/app ./app
COPY src/aiops/runbooks.yaml ./runbooks.yaml

RUN useradd --system --uid 10001 aiops
USER 10001
EXPOSE 8080
CMD ["python", "-m", "app.main"]
