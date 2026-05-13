FROM python:3.12-slim

# Don't write .pyc files; flush stdout immediately so `docker compose logs` is live.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies first so this layer is cached unless requirements change.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy the rest of the source.
COPY . .

CMD ["python", "bot.py"]
