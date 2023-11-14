FROM python:3.9-slim

WORKDIR /app
# ENV TRIVY_CACHE_DIR=/root/.cache/trivy
# Install kubectl
ADD https://storage.googleapis.com/kubernetes-release/release/v1.22.0/bin/linux/amd64/kubectl /usr/local/bin/kubectl
RUN chmod +x /usr/local/bin/kubectl

# Install trivy
RUN apt-get update && \
    apt-get install -y wget apt-transport-https gnupg lsb-release && \
    wget -qO - https://aquasecurity.github.io/trivy-repo/deb/public.key | gpg --dearmor -o /usr/share/keyrings/trivy-archive-keyring.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/trivy-archive-keyring.gpg] https://aquasecurity.github.io/trivy-repo/deb $(lsb_release -sc) main" | tee /etc/apt/sources.list.d/trivy.list > /dev/null && \
    apt-get update && \
    apt-get install -y trivy && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY scanner.py .
COPY worker.py .
COPY cpu_ut.py .
COPY K_connection.py .
COPY requirements.txt .
COPY main_communication.py .
RUN pip install --no-cache-dir -r requirements.txt --timeout 600

CMD ["python", "worker.py"]
