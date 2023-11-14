FROM python:3.9-slim

WORKDIR /app

COPY main-mape.py .
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Install kubectl
RUN apt-get update && \
    apt-get install -y apt-transport-https gnupg2 curl && \
    curl -s https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key add - && \
    echo "deb https://apt.kubernetes.io/ kubernetes-xenial main" | tee -a /etc/apt/sources.list.d/kubernetes.list && \
    apt-get update && \
    apt-get install -y kubectl && \
    apt-get remove -y apt-transport-https gnupg2 curl && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

CMD ["python", "./main-mape.py"]
