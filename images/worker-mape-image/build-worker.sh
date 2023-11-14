#!/bin/bash

# Build the Docker image
docker build -t worker .

# Save the Docker image
docker save -o worker.tar worker:latest

# Load the Docker image
docker load -i worker.tar