FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY db ./db
RUN pip install --no-cache-dir .

# long-polling worker: no ports exposed, single replica
CMD ["python", "-m", "launch11bot.main"]
