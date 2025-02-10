# Use Debian as the base image
FROM debian:bullseye

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies and wkhtmltopdf
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-setuptools python3-wheel \
    xfonts-75dpi xfonts-base \
    wget fontconfig libxrender1 libjpeg62-turbo libpng-dev \
    libx11-6 libxext6 libssl-dev \
    wkhtmltopdf && \
    rm -rf /var/lib/apt/lists/* /tmp/*

# Set working directory
WORKDIR /app

# Copy application code
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY . .

# Expose Flask port
EXPOSE 5000

# Run the app
CMD ["python3", "app.py"]
