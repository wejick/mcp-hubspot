# Use Python base image
FROM python:3.12-slim-bookworm

# Install the project into `/app`
WORKDIR /app

# Copy the entire project
COPY . /app

# Install the package
RUN pip install --no-cache-dir .

# Create models directory
RUN mkdir -p /app/models

# Pre-download models
RUN python -c "from sentence_transformers import SentenceTransformer; \
    model = SentenceTransformer('all-MiniLM-L6-v2'); \
    model.save('/app/models/all-MiniLM-L6-v2')"

# Run the server
ENTRYPOINT ["mcp-server-hubspot"] 