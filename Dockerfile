# A single-stage image is right here: the app is pure Python with no build step and no
# compiled dependencies, so a builder stage would add complexity without shrinking anything.
FROM python:3.11-slim

# PYTHONDONTWRITEBYTECODE: the image is immutable, .pyc files are just layer weight.
# PYTHONUNBUFFERED: without it, logs sit in a buffer and arrive late, or not at all when a
# container is killed -- which is exactly when you need them.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies are copied and installed before the source, so editing a Python file reuses
# the cached install layer instead of reinstalling everything.
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY . .

# Run as a non-root user. The data directory is created and handed over up front, because a
# process that cannot write its own SQLite file fails in a confusing way at the first write
# rather than at startup.
RUN useradd --create-home --shell /bin/bash app \
    && mkdir -p /app/data \
    && chown -R app:app /app
USER app

ENV DJANGO_SQLITE_PATH=data/db.sqlite3

EXPOSE 8000

# `sh -c` so the migration runs in the same container, before the server accepts traffic.
CMD ["sh", "-c", "python manage.py migrate --no-input && gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --access-logfile - --error-logfile -"]
