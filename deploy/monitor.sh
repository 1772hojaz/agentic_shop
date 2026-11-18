#!/bin/sh
# Lightweight host and container resource checks without a monitoring agent.
set -eu
date -u
free -m
df -h /
docker compose stats --no-stream
curl --fail --silent --show-error http://127.0.0.1:8080/ready
