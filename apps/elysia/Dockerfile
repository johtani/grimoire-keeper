FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install elysia
RUN pip install elysia-ai

# Expose port
EXPOSE 3000

# Set environment variables
ENV WEAVIATE_URL=http://weaviate:8080

# Run elysia
CMD ["elysia", "start", "--host", "0.0.0.0", "--port", "3000"]