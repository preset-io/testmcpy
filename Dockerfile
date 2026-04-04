FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
COPY testmcpy/ testmcpy/
RUN pip install --no-cache-dir .
EXPOSE 8000
CMD ["testmcpy", "serve", "--host", "0.0.0.0", "--port", "8000"]
