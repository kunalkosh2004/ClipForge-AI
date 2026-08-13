FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl unzip ca-certificates fonts-noto-core \
    && curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/opt/deno sh \
    && ln -s /opt/deno/bin/deno /usr/local/bin/deno \
    && mkdir -p /opt/opencv \
    && curl -fsSL https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx \
        -o /opt/opencv/face_detection_yunet.onnx \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY vendor ./vendor
COPY src ./src

# Install the vendored motion-caption wheel FIRST so its bundled Noto Sans
# fonts ship in the image; then the editable install satisfies the
# `motion-caption>=0.1.3` pin from the vendored copy instead of PyPI.
RUN pip install ./vendor/motion_caption-0.1.3-py3-none-any.whl \
    && pip install -e .

COPY . .

EXPOSE 8000

CMD ["uvicorn", "clipforge.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS dev
RUN pip install -e '.[dev]'
