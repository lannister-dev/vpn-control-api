ARG PYTHON_BUILD_IMAGE=harbor.lannister-dev.ru/docker-hub/library/python:3.10
ARG PYTHON_RUNTIME_IMAGE=harbor.lannister-dev.ru/docker-hub/library/python:3.10-slim

FROM ${PYTHON_BUILD_IMAGE} AS compile-image

ENV VIRTUAL_ENV=/opt/venv
RUN python -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

FROM ${PYTHON_RUNTIME_IMAGE} AS build-image

COPY --from=compile-image /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app
COPY . /app

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
