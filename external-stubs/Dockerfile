FROM python:3.12-slim-trixie
WORKDIR /srv
RUN pip install --no-cache-dir fastapi~=0.115 uvicorn~=0.32 \
 && useradd -r -u 10001 app
COPY main.py .
USER app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8081"]
