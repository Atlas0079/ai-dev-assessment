ARG BASE_IMAGE
FROM ${BASE_IMAGE}
WORKDIR /opt/environment
COPY requirements.lock .
RUN python -m pip install --no-cache-dir --only-binary=:all: --require-hashes -r requirements.lock && python -m pip check
ENV PIP_NO_INDEX=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
