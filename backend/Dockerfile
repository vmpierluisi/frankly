FROM python:3.11-slim

WORKDIR /app

# System deps for PDF/DOCX parsing (pypdf is pure-python; python-docx is pure-python;
# but we install build-essential for any wheels that need compilation).
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
