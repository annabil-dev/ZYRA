FROM python:3.11.11-slim-bookworm@sha256:081075da77b2b55c23c088251026fb69a7b2bf92471e491ff5fd75c192fd38e5
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
COPY runtime-requirements.txt /opt/zyra/runtime-requirements.txt
RUN pip install --no-cache-dir -r /opt/zyra/runtime-requirements.txt \
    && python -m playwright install --with-deps chromium \
    && chmod -R a+rX /ms-playwright
COPY contract.py runner.py scoring.py /opt/zyra/
WORKDIR /app
