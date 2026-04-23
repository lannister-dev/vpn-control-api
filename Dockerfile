ARG PYTHON_BUILD_IMAGE=python:3.10
ARG PYTHON_RUNTIME_IMAGE=python:3.10-slim
ARG NODE_BUILD_IMAGE=node:20-alpine

FROM ${NODE_BUILD_IMAGE} AS ui-build
WORKDIR /ui
COPY services/admin_ui/frontend/package.json services/admin_ui/frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY services/admin_ui/frontend/ ./
RUN npm run build

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
COPY --from=ui-build /ui/dist /app/services/admin_ui/static/v2

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
