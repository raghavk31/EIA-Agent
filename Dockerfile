FROM python:3.12-slim

# WeasyPrint runtime libs (pango/cairo/gdk-pixbuf)
# pycairo (xhtml2pdf dep) uses a prebuilt wheel on py3.12 — no libcairo-dev needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD gunicorn app:app --bind 0.0.0.0:$PORT --timeout 180 --workers 2
