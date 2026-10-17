FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY amd ./amd
COPY frontend ./frontend
COPY assets/refinery ./assets/refinery
EXPOSE 8765
CMD ["python", "-m", "amd.server", "--host", "0.0.0.0"]
