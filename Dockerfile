FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

ARG MF6_VERSION=6.7.0

RUN set -eux; \
    mkdir -p /tmp/mf6; \
    curl --fail --location --retry 5 --retry-delay 5 --retry-all-errors --continue-at - \
        "https://github.com/MODFLOW-ORG/modflow6/releases/download/${MF6_VERSION}/mf${MF6_VERSION}_linux.zip" \
        -o /tmp/mf6/mf6.zip; \
    unzip -q /tmp/mf6/mf6.zip -d /tmp/mf6; \
    install -m 0755 "/tmp/mf6/mf${MF6_VERSION}_linux/bin/mf6" /usr/local/bin/mf6; \
    install -m 0755 "/tmp/mf6/mf${MF6_VERSION}_linux/bin/libmf6.so" /usr/local/bin/libmf6.so; \
    /usr/local/bin/mf6 -v; \
    rm -rf /tmp/mf6

COPY requirements.txt ./
RUN pip install --no-cache-dir --default-timeout=180 --retries=10 -r requirements.txt

COPY . /app

RUN if [ -d /app/solvers ]; then \
        find /app/solvers -maxdepth 1 -type f -exec chmod +x {} +; \
    fi

# Run as a non-root user. /data/numerical_jobs is pre-created and chowned so
# the named volume mounted there inherits this ownership on first use.
RUN useradd --system --create-home --uid 10001 cast \
    && mkdir -p /data/numerical_jobs /tmp/numerical_runs \
    && chown -R cast:cast /app /data /tmp/numerical_runs

ENV PYTHONUNBUFFERED=1 \
    FLASK_HOST=0.0.0.0 \
    FLASK_PORT=5000 \
    PANEL_HOST=0.0.0.0 \
    PANEL_PORT=5007 \
    MF6_EXE=/usr/local/bin/mf6 \
    MPLCONFIGDIR=/tmp/matplotlib

USER cast

EXPOSE 5000 5007
