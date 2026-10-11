FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir . && useradd --create-home bot && mkdir /data && chown bot /data
COPY roles.yaml ./
USER bot
ENV DB_PATH=/data/orchestrator.db ROLES_PATH=/app/roles.yaml
CMD ["orchestrator", "bot"]
