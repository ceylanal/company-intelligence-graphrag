# Production Packaging and Deployment Guide

This guide details the packaging, environment management, and service orchestration architecture for **Company Intelligence GraphRAG**.

---

## 1. Environment Architecture & Profiles

The system uses **Pydantic Settings** for type-safe environment configuration supporting four deployment modes:

| Environment | Description | Database Targets |
| :--- | :--- | :--- |
| `development` | Local development environment (default) | Local Docker containers |
| `test` / `testing` | CI/CD automated test suite | Embedded / Mock stores |
| `staging` | Staging environment with cloud DBs or staging cluster | Cloud / Remote cluster |
| `production` | Production Cloud Run / container cluster | Production Qdrant & Neo4j |

### Cloud vs. Local Connection Toggles
Switch between local containers and managed cloud databases via environment variables in `.env`:

```env
# Qdrant Cloud Cluster
QDRANT_URL=https://your-cluster-id.qdrant.tech
QDRANT_API_KEY=your-qdrant-cloud-api-key
QDRANT_USE_CLOUD=true

# Neo4j Aura Cloud
NEO4J_URI=neo4j+s://your-db-id.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your-aura-password
NEO4J_USE_CLOUD=true
```

---

## 2. Docker Compose Profiles & Resource Limits

Docker Compose services are separated into distinct execution profiles to minimize memory and resource overhead on development machines (e.g. MacBook Air M2 16GB RAM):

```
                     ┌──────────────────────────────────────────────┐
                     │          Docker Compose Profiles             │
                     └──────────────────────┬───────────────────────┘
                                            │
           ┌────────────────────────────────┼──────────────────────────────┐
           ▼                                ▼                              ▼
    ┌─────────────┐                 ┌───────────────┐              ┌───────────────┐
    │    core     │                 │ observability │              │   load-test   │
    ├─────────────┤                 ├───────────────┤              ├───────────────┤
    │ - API (1GB) │                 │ - Placeholder │              │ - Locust      │
    │ - Qdrant(1G)│                 │   agents      │              │   (512MB)     │
    │ - Neo4j (2G)│                 └───────────────┘              └───────────────┘
    └─────────────┘
```

| Service | Profile | Memory Limit | CPU Limit | Healthcheck Endpoint |
| :--- | :--- | :--- | :--- | :--- |
| `api` | `core` | 1 GB | 1.0 cpus | `http://localhost:8000/health/live` |
| `qdrant` | `core` | 1 GB | 1.0 cpus | `./qdrant --version` / `:6333/healthz` |
| `neo4j` | `core` | 2 GB | 2.0 cpus | `http://localhost:7474` |
| `locust` | `load-test` | 512 MB | 0.5 cpus | `http://localhost:8089` |

---

## 3. Fresh-Clone Quickstart

Follow these steps to run the project from a fresh clone:

### Step 1: Copy Environment Template
```bash
cp .env.example .env
```

### Step 2: Install Project Dependencies
```bash
make install
```

### Step 3: Start Core Docker Services
```bash
make services-up
```

### Step 4: Verify System Health
```bash
make doctor
```

### Step 5: Start Local API Web Server
```bash
make api
```
Access the API documentation at [http://localhost:8000/docs](http://localhost:8000/docs).

---

## 4. Health & Status Endpoints

| Endpoint | HTTP Method | Purpose | Response Code |
| :--- | :--- | :--- | :--- |
| `/health/live` | `GET` | Container Liveness probe | `200 OK` |
| `/health/ready` | `GET` | Independent database connectivity check | `200 OK` (healthy) / `503 Service Unavailable` (degraded) |
| `/version` | `GET` | Application & Python version details | `200 OK` |

### Sample Readiness Probe Output (Degraded State)
```json
{
  "status": "unhealthy",
  "environment": "development",
  "components": {
    "qdrant": {
      "status": "ok",
      "url": "http://qdrant:6333",
      "details": "Online"
    },
    "neo4j": {
      "status": "error",
      "url": "http://neo4j:7474",
      "details": "Connection failed: HTTP 500"
    }
  }
}
```

---

## 5. Development & Verification Commands

```bash
# Run full static check and unit test suite
make check

# Build production Docker image
make docker-build

# Run API health smoke tests
make smoke-test

# Run load test via Locust (requires load-test profile)
docker compose --profile load-test up
```
