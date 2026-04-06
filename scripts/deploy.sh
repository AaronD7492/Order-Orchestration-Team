#!/bin/bash
set -e

docker stop order-orchestration-container || true
docker rm order-orchestration-container || true

docker build -t order-orchestration-service .

docker run -d \
  --name order-orchestration-container \
  -p 5001:5000 \
  -e DB_HOST=143.198.35.133 \
  -e DB_PORT=5432 \
  -e DB_NAME=farmforkdb \
  -e DB_USER=orders \
  -e DB_PASSWORD=orchestrate \
  -e TEAM_NAME="Order Orchestration" \
  order-orchestration-service