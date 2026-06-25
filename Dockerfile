FROM python:3.12

WORKDIR /auth_api

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=bind,source=requirements.txt,target=requirements.txt \
    python -m pip install -U pip wheel && python -m pip install -r requirements.txt

COPY . .
RUN chmod +x run_app.sh

ENTRYPOINT ["./run_app.sh"]
