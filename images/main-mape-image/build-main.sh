#!/bin/bash

# Build the Docker image
docker build -t main-mape .

# Save the Docker image
docker save -o main-mape-image.tar main-mape:latest

# Load the Docker image
docker load -i main-mape-image.tar