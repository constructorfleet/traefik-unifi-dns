FROM python:3.13-alpine
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
# The state volume is initialized by Docker as root. The default deployment
# talks only to the read-only socket proxy; direct socket mode is explicitly a
# compatibility fallback and already has root-equivalent Docker authority.
EXPOSE 8080
CMD ["python", "-m", "app.main"]
