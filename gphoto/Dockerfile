# One image, three jobs: incoming, google and web. Build from the repo root.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends libimage-exiftool-perl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY gphoto/requirements.txt ./gphoto/
RUN pip install --no-cache-dir -r gphoto/requirements.txt
COPY gphoto ./gphoto

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
ARG VERSION=unknown
ENV GPHOTO_VERSION=${VERSION}
USER 1000:1000
