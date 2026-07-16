FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .   # migrations ship inside the package (package-data)

# long-polling worker: no ports exposed, single replica
CMD ["python", "-m", "launch11bot.main"]
