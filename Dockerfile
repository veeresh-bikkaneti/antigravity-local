FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 HOST=0.0.0.0 PORT=8000

# /app/.memory holds the search index. World-writable so a forced user id (--user 12345) can create it too.
RUN useradd --create-home app && mkdir -p /app/.memory && chown app /app && chmod 777 /app/.memory
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=app:app . .
USER app

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=4s --start-period=20s \
  CMD python -c "import os,urllib.request as u; u.urlopen('http://127.0.0.1:'+os.environ['PORT']+'/healthz', timeout=3)"

# 8000 is the port *inside* the container. Publish with a random host port:
#   docker run --rm -p 127.0.0.1::8000 antigravity-local   (then: docker port <container> 8000)
CMD ["python", "serve.py"]
