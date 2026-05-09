# 👻 Chost Hunter

> **C**ontainer + **Ghost** Hunter: An AI-driven Container Resource Optimization System.

**Chost Hunter** is an AIOps-based resource optimization solution designed to identify idle or over-provisioned Docker containers and safely right-size their CPU and memory limits using time-series predictions.

---

## 🌟 Key Features

| Feature | Description |
|---|---|
| 🔍 AI-Powered Prediction | Uses an LSTM model to estimate future CPU and memory demand from time-series metrics |
| 🛡️ Safe Rollback Mechanism | Automatically restores previous limits if instability is detected |
| 🤖 Automated Optimization | Monitoring ⮕ Prediction ⮕ Recommendation ⮕ Policy Check ⮕ Resource Update |
| 📦 One-Command Deployment | Deploy the full stack using Docker Compose without cloning the repository |

---

## 🏗️ System Architecture

![Chost Hunter System Diagram](images/system_diagram.png)

### Workflow

| Step | Description |
|---|---|
| 1 | `cAdvisor` collects real-time container metrics |
| 2 | `Prometheus` stores time-series metrics |
| 3 | `Grafana` visualizes infrastructure metrics |
| 4 | The `AI Agent` performs LSTM inference using Prometheus metrics |
| 5 | The agent recommends or applies optimized Docker resource limits |
| 6 | The watchdog restores previous limits if instability is detected |

---

## 🛠️ Technology Stack

| Category | Technologies |
|---|---|
| Infrastructure | Docker |
| Monitoring | Prometheus, cAdvisor |
| Visualization | Grafana |
| AI/ML | PyTorch, Scikit-learn |
| Backend | Python 3.11 |
| Container Control | Docker SDK for Python |

---

## 🚀 Quick Start

Deploy the full Chost Hunter stack without cloning the repository.

### 1. Download the Docker Compose file

```bash
curl -O https://raw.githubusercontent.com/jagggged/chost-hunter/main/docker-compose.yml
```

### 2. Launch Chost Hunter

```bash
docker compose up -d
```

Docker Compose automatically downloads and starts:

| Service |
|---|
| AI Agent |
| Prometheus |
| Grafana |
| cAdvisor |
| Alertmanager |

### 3. Verify deployment

```bash
docker compose ps
docker compose logs --tail=50
```

---

## 🌐 Service Endpoints

| Service | URL |
|---|---|
| Grafana | http://localhost:3000 |
| Prometheus | http://localhost:9090 |
| Alertmanager | http://localhost:9093 |
| cAdvisor | http://localhost:8080 |
| AI Agent API | http://localhost:8000 |

### Grafana Default Credentials

| Field | Value |
|---|---|
| Username | `admin` |
| Password | `admin` |

---

## Runtime Control Policy

| Label | Description |
|---|---|
| `chost-hunter.policy=auto` | Automatically apply AI recommendations |
| `chost-hunter.policy=advisory` | Show recommendations only |
| `chost-hunter.skip=true` | Ignore the container completely |

---

## Control API

| Endpoint | Description |
|---|---|
| `/api/health` | Health check |
| `/api/actions/latest` | Latest optimization action |
| `/api/recommendations/latest` | Latest AI recommendation |
| `/api/containers` | Managed container list |
| `/api/state` | Global runtime state |

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/actions/latest
curl http://127.0.0.1:8000/api/recommendations/latest
curl http://127.0.0.1:8000/api/containers
curl http://127.0.0.1:8000/api/state
```