# Use a lightweight Python image with Playwright system dependencies
FROM mcr.microsoft.com/playwright:python-1.48.0

# Set working directory
WORKDIR /app

# Copy requirements first (better caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Tell Flask to use the port Railway provides
ENV PORT=5000
EXPOSE $PORT

# Run with gunicorn (single worker + threads for Playwright)
CMD gunicorn --worker-class gthread --threads 4 --bind 0.0.0.0:$PORT server:app
