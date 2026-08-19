# GRMT backend container — used by docker-compose.yml's `full` profile and
# as the base for Render/Railway deployment (master build document §2.6).
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Run migrations, then start the server. In a real deployment, split these
# into a separate migration step (a release-phase command on
# Render/Railway) rather than running migrations on every container start —
# this combined form is a reasonable default for local/demo use.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
