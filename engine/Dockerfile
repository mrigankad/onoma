FROM python:3.13-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY onoma ./onoma
RUN pip install --no-cache-dir .

ENV ONOMA_DB=/data/onoma.db \
    ONOMA_CORS=http://localhost:3000
VOLUME ["/data"]
EXPOSE 8000

CMD ["sh", "-c", "onoma --db $ONOMA_DB serve --host 0.0.0.0 --port 8000"]
