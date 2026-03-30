FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    curl \
    gfortran \
    git \
    libgfortran5 \
    make \
    meson \
    ninja-build \
    unzip \
    && rm -rf /var/lib/apt/lists/*

ARG MF2005_URL=https://water.usgs.gov/water-resources/software/MODFLOW-2005/MF2005.1_12u.zip
ARG MT3DMS_GIT_URL=https://github.com/MODFLOW-USGS/mt3dms.git
ARG MT3DMS_GIT_REF=1a8d6139c31bea7df8c551cc5fa6e7de5361e4c3

RUN set -eux; \
    mkdir -p /tmp/build-mf2005; \
    curl -L "$MF2005_URL" -o /tmp/build-mf2005/mf2005.zip; \
    unzip -q /tmp/build-mf2005/mf2005.zip -d /tmp/build-mf2005; \
    make -C /tmp/build-mf2005/MF2005.1_12u/make; \
    install -m 0755 /tmp/build-mf2005/MF2005.1_12u/make/mf2005 /usr/local/bin/mf2005; \
    rm -rf /tmp/build-mf2005

RUN set -eux; \
    git clone "$MT3DMS_GIT_URL" /tmp/build-mt3dms; \
    cd /tmp/build-mt3dms; \
    git checkout "$MT3DMS_GIT_REF"; \
    sed -i "s|DATA FORM/'BINARY'/|      DATA FORM/'UNFORMATTED'/|" src/filespec.inc; \
    meson setup builddir --prefix=/usr/local; \
    meson compile -C builddir; \
    meson install -C builddir; \
    rm -rf /tmp/build-mt3dms

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

RUN if [ -d /app/solvers ]; then \
        find /app/solvers -maxdepth 1 -type f -exec chmod +x {} +; \
    fi

ENV PYTHONUNBUFFERED=1 \
    FLASK_HOST=0.0.0.0 \
    FLASK_PORT=5000 \
    PANEL_HOST=0.0.0.0 \
    PANEL_PORT=5007 \
    MF2005_EXE=/usr/local/bin/mf2005 \
    MT3DMS_EXE=/usr/local/bin/mt3dms

EXPOSE 5000 5007
