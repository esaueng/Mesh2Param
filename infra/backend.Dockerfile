# syntax=docker/dockerfile:1.7

ARG PYTHON_IMAGE=python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.11.28@sha256:0f36cb9361a3346885ca3677e3767016687b5a170c1a6b88465ec14aefec90aa
ARG BACKEND_PLATFORM=linux/amd64

FROM --platform=${BACKEND_PLATFORM} ${UV_IMAGE} AS uv-bin

FROM --platform=${BACKEND_PLATFORM} ${PYTHON_IMAGE} AS backend-base

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        ca-certificates \
        libgl1 \
        libx11-6 \
        libxext6 \
        libxrender1 \
        libxcb1 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONNOUSERSITE=1 \
    PYTHONSAFEPATH=1

FROM backend-base AS builder

COPY --from=uv-bin /uv /uvx /usr/local/bin/
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_CACHE_DIR=/root/.cache/uv
WORKDIR /build

COPY pyproject.toml uv.lock uv.toml README.md ./
COPY packages/contracts/pyproject.toml packages/contracts/pyproject.toml
COPY packages/contracts/python packages/contracts/python
COPY packages/contracts/schema packages/contracts/schema
COPY engine engine
COPY services services

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

# The image is not accepted unless its exact locked OCCT stack completes a real STEP roundtrip.
RUN /opt/venv/bin/python -P - <<'PY'
import tempfile
from pathlib import Path

import cadquery as cq
from OCP.BRepCheck import BRepCheck_Analyzer
from cadquery import exporters, importers

shape = cq.Workplane("XY").box(12.0, 10.0, 6.0).faces(">Z").workplane().hole(3.0)
with tempfile.TemporaryDirectory(prefix="mesh2param-image-smoke-") as directory:
    step_path = Path(directory) / "roundtrip.step"
    exporters.export(shape, str(step_path))
    restored = importers.importStep(str(step_path))
    if len(restored.solids().vals()) != 1:
        raise RuntimeError("STEP smoke did not reimport exactly one solid")
    if not BRepCheck_Analyzer(restored.val().wrapped).IsValid():
        raise RuntimeError("STEP smoke reimported an invalid B-Rep")
PY

FROM backend-base AS runtime

RUN groupadd --gid 10001 mesh2param \
    && useradd --uid 10001 --gid 10001 --no-create-home --home-dir /tmp/home \
        --shell /usr/sbin/nologin mesh2param \
    && install -d -o 10001 -g 10001 -m 0750 \
        /app \
        /var/lib/mesh2param \
        /var/lib/mesh2param/db \
        /var/lib/mesh2param/jobs \
        /var/lib/mesh2param/storage \
    && install -d -o root -g root -m 0755 /usr/share/doc/mesh2param

COPY --from=builder /opt/venv /opt/venv
COPY --chown=10001:10001 samples/generated /app/samples/generated
COPY LICENSE NOTICE THIRD_PARTY_NOTICES.md /usr/share/doc/mesh2param/
COPY licenses /usr/share/doc/mesh2param/licenses

ENV PATH=/opt/venv/bin:$PATH \
    HOME=/tmp/home \
    XDG_CACHE_HOME=/tmp/cache \
    MPLCONFIGDIR=/tmp/matplotlib \
    MESH2PARAM_DATA_DIR=/var/lib/mesh2param
WORKDIR /app
USER 10001:10001
EXPOSE 8000

CMD ["python", "-P", "-m", "mesh2param_api.cli"]
