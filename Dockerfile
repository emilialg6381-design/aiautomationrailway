FROM mcr.microsoft.com/playwright:python-1.48.0

WORKDIR /app

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install browsers into the same path (if needed)
RUN playwright install chromium

COPY . .

ENV PORT=5000
EXPOSE $PORT

CMD gunicorn --worker-class gthread --threads 4 --bind 0.0.0.0:$PORT server:app
