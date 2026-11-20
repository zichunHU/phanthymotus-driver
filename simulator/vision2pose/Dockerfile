FROM bj-warehouse.tencentcloudcr.com/phanthy-motus/core:release.261118.56edda4@sha256:1e7bbd56d70fb53b8c7a9549e0dfb02a793b7f78d6495030c0ce2d0487948031

WORKDIR /vision2pose
ENV UV_PYTHON_DOWNLOADS=never UV_HTTP_TIMEOUT=120 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --index-url https://pypi.org/simple --python /usr/bin/python3
RUN printf '%s\n' \
      'deb https://ports.ubuntu.com/ubuntu-ports/ jammy main' \
      'deb https://ports.ubuntu.com/ubuntu-ports/ jammy-updates main' \
      'deb https://ports.ubuntu.com/ubuntu-ports/ jammy-security main' \
      > /etc/apt/sources.list \
    && apt-get update -o Acquire::Languages=none \
    && apt-get install -y --no-install-recommends libegl1 libgles2 libegl-mesa0 \
    && rm -rf /var/lib/apt/lists/*
