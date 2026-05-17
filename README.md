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

The provisioned Grafana dashboard includes the Chost Hunter AI panel plugin on
the right side. The plugin calls the AI Agent Control API directly and exposes:

- latest recommendations
- manual Apply
- per-container policy selector
- Autopilot toggle
- fine-tuning state/settings
- Slack notification settings
- recent action history

---

## Runtime Control Policy

| Label | Description |
|---|---|
| `chost-hunter.policy=auto` | Automatically apply AI recommendations |
| `chost-hunter.policy=advisory` | Show recommendations only |
| `chost-hunter.skip=true` | Ignore the container completely |

```yaml
labels:
  - "chost-hunter.policy=auto"      # apply AI recommendations with docker update
  - "chost-hunter.policy=advisory"  # print recommendations only
  - "chost-hunter.skip=true"        # ignore the container completely
```

If a container has no Chost Hunter label and either `CpuQuota` or `Memory` is
`0`, Docker treats that limit as unlimited. Chost Hunter handles this case as
`advisory` by default, even when `DEFAULT_POLICY` is `auto`, because an operator
may have intentionally left a critical service unlimited. To let the AI create
the first limit for an unlimited container, add `chost-hunter.policy=auto`
explicitly.

Recommendation output is conservatively capped after inference. By default,
finite container limits are not increased above their current value
(`MAX_LIMIT_INCREASE_RATIO=1.0`), and absolute caps prevent runaway predictions
from becoming huge Docker limits (`MAX_CPU_QUOTA=4.0`,
`MAX_MEMORY_BYTES=2147483648`).

---

## Runtime Fine-tuning

The runtime loop performs inference only. Online fine-tuning is disabled by
default (`ENABLE_ONLINE_FINETUNE = False`) so model training overhead cannot
outweigh the resource savings during normal operation.

To test runtime fine-tuning explicitly, set:

```bash
ENABLE_ONLINE_FINETUNE=true
```

It can also be switched at runtime from the prototype dashboard or through the
Control API:

```bash
curl -X POST http://127.0.0.1:8000/api/state/finetune \
  -H "Content-Type: application/json" \
  -d "{\"enabled\":true}"
```

For short local demos, you can lower the sample threshold without changing the
production default:

```bash
ENABLE_ONLINE_FINETUNE=true FINETUNE_MIN_SAMPLES=8 FINETUNE_EPOCHS=1
```

The Docker Compose file does not require a `.env` file. It defaults to the
published GHCR agent image and pretrained inference mode, so the Quick Start
commands above are enough for normal deployment.

For local image verification before publishing:

```bash
docker build -t chost-hunter-agent:local .
AI_AGENT_IMAGE=chost-hunter-agent:local docker compose up -d ai-agent
```

When enabled, the agent keeps `models/pretrained.pt` as the master model,
creates `models/runtime/active.pt` for runtime inference, and trains candidate
models from recent Prometheus samples. A candidate is promoted only when its
validation loss is no worse than the current active model and the run stays
within the configured duration budget. Fine-tuning run history is written to
`logs/finetune_runs.jsonl` and exposed through:

```bash
curl http://127.0.0.1:8000/api/finetune/latest
curl http://127.0.0.1:8000/api/finetune/runs?limit=20
```

Fine-tuning settings can also be inspected and updated through:

```bash
curl http://127.0.0.1:8000/api/settings/finetune
curl -X POST http://127.0.0.1:8000/api/settings/finetune \
  -H "Content-Type: application/json" \
  -d "{\"interval_sec\":21600,\"initial_delay_sec\":300,\"auto_promote\":true}"
```

---

## Action Log

Every control-loop decision is appended to `logs/actions.jsonl`.

Each line contains a single JSON object with:

- `container`: target container name
- `policy`: `auto`, `advisory`, or `skip`
- `status`: `recommended`, `applied`, `skipped`, or `failed`
- `current_limits`, `recommended_limits`, `applied_limits`, `previous_limits`
- `reason` or `error` when the agent did not apply a recommendation

Quick inspection:

```bash
tail -n 5 logs/actions.jsonl
```

---

## Control API

| Endpoint | Description |
|---|---|
| `/api/health` | Health check |
| `/api/actions?limit=20` | Recent action log entries |
| `/api/actions/latest` | Latest optimization action |
| `/api/recommendations/latest` | Latest AI recommendation |
| `/api/containers` | Managed container list |
| `/api/state` | Global runtime state |
| `/api/finetune/latest` | Latest runtime fine-tuning run |
| `/api/finetune/runs?limit=20` | Runtime fine-tuning history |
| `/api/settings/finetune` | Runtime fine-tuning settings |
| `/api/settings/notifications` | Slack notification settings |

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/actions?limit=20
curl http://127.0.0.1:8000/api/actions/latest
curl http://127.0.0.1:8000/api/recommendations/latest
curl http://127.0.0.1:8000/api/containers
curl http://127.0.0.1:8000/api/state
curl http://127.0.0.1:8000/api/finetune/latest
```

The dashboard should read from these endpoints instead of parsing
`logs/actions.jsonl` directly. The JSONL file remains the operator-visible audit
trail.

Dashboard policy changes are stored as runtime overrides in
`logs/policy_overrides.json`. Runtime overrides take precedence over Docker
policy labels so operators can move a container between auto, advisory, and skip
from the dashboard during a demo or live run.

The dashboard's Auto Resource Optimization toggle is the global autopilot kill
switch stored in `logs/global_state.json`. When it is off, containers whose
effective policy is `auto` still produce recommendations, but the agent does not
run `docker update`.

---

## Slack Notifications

Non-developer users can connect Slack from the dashboard. Paste the incoming
webhook URL into the Slack notification box, click Save, then click Test. The
dashboard stores this local runtime setting in `logs/settings.json`, which is
ignored by git.

Developers can also set `SLACK_WEBHOOK_URL` as an environment variable:

```bash
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
```

On Windows PowerShell:

```powershell
$env:SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
```

Dashboard settings take priority over the environment variable when both are
present.

Notified statuses are:

- `recommended`
- `applied`
- `failed`
- `policy_updated`
- `autopilot_updated`
- `finetune_updated`
- `finetune_settings_updated`

Every notification attempt is also written to `logs/notifications.jsonl`. If no
webhook URL is configured, Chost Hunter records the notification as `disabled`
there, which makes local verification possible without a real Slack workspace.
