FROM node:22-slim AS web-build

WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build


FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY server/ ./server/
COPY service.py ./
COPY agent/ ./agent/
COPY executors/ ./executors/
COPY core/ ./core/
COPY safety/ ./safety/
COPY llm/ ./llm/
COPY analysis/ ./analysis/
COPY viz/ ./viz/
COPY loaders/ ./loaders/
COPY --from=web-build /web/dist ./web/dist

# 非 root 运行：生成代码在独立子进程中 exec、超时强杀；降权可缩小被突破时的影响面
RUN useradd -m appuser && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000"]
