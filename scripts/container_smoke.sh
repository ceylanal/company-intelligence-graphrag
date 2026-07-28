#!/usr/bin/env sh
set -eu

image="${1:-company-graphrag:latest}"
container_name="company-graphrag-smoke-$$"

cleanup() {
  docker rm -f "$container_name" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

docker run -d --name "$container_name" -p 127.0.0.1::8000 \
  -e ENVIRONMENT=test \
  -e TELEMETRY_ENABLED=false \
  "$image" >/dev/null

host_port="$(docker port "$container_name" 8000/tcp | sed 's/.*://')"
attempt=0
while [ "$attempt" -lt 30 ]; do
  if curl --fail --silent "http://127.0.0.1:${host_port}/health/live" >/dev/null; then
    curl --fail --silent "http://127.0.0.1:${host_port}/version" >/dev/null
    exit 0
  fi
  attempt=$((attempt + 1))
  sleep 1
done

docker logs "$container_name"
exit 1
