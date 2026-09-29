FROM python:3.11.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
COPY runtime-requirements.txt /opt/zyra/runtime-requirements.txt
RUN pip install --no-cache-dir -r /opt/zyra/runtime-requirements.txt \
    && python -m playwright install --with-deps chromium \
    && chmod -R a+rX /ms-playwright
COPY contract.py runner.py scoring.py /opt/zyra/
WORKDIR /app
