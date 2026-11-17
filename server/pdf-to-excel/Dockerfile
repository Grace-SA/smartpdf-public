FROM node:24-bookworm-slim AS node
FROM python:3.12-slim-bookworm
COPY --from=node /usr/local/bin/node /usr/local/bin/node
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libgl1 libstdc++6 tini && rm -rf /var/lib/apt/lists/* && useradd --uid 1000 --create-home converter
WORKDIR /app
COPY server/pdf-to-excel/requirements-lock.txt ./requirements-lock.txt
RUN python3 -m venv /opt/excel && /opt/excel/bin/pip install --no-cache-dir torch==2.15.0 torchvision==0.29.1 --index-url https://download.pytorch.org/whl/cpu && /opt/excel/bin/pip install --no-cache-dir -r requirements-lock.txt
COPY server/pdf-to-excel/ ./server/pdf-to-excel/
COPY scripts/pdf-to-excel/prepare-models.py ./scripts/pdf-to-excel/prepare-models.py
RUN /opt/excel/bin/python scripts/pdf-to-excel/prepare-models.py /opt/models
ENV PDF_EXCEL_PYTHON=/opt/excel/bin/python PDF_EXCEL_MODELS=/opt/models PDF_EXCEL_OCR=true NODE_ENV=production PDF_EXCEL_HOST=0.0.0.0 HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1
USER converter
EXPOSE 4290
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["node", "server/pdf-to-excel/service.mjs"]
