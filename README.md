# 👻 Chost Hunter

> **C**ontainer + **Ghost** Hunter: An AI-driven Container Resource Optimization System.

**Chost Hunter** is an AIOps-based resource optimization solution designed to identify idle or over-provisioned Docker containers and safely right-size their CPU and memory limits using time-series predictions.

## 🌟 Key Features

* **🔍 AI-Powered Prediction**: Goes beyond static thresholds by using an **LSTM** model to analyze time-series metric patterns and estimate future CPU/memory demand.
* **🛡️ Safety First (Rollback)**: Before applying a tighter resource limit, the agent records the previous limits and uses a watchdog to roll back if usage crosses the safety threshold.
* **🤖 Automated Lifecycle**: A seamless end-to-end pipeline: Monitoring ⮕ Prediction ⮕ Recommendation ⮕ Policy Check ⮕ Resource Update.
* **Standard Tech Stack**: Built on industry-standard open-source tools including cAdvisor, Prometheus, Grafana, and Docker SDK for high reliability and portability.

## 🏗️ System Architecture

This diagram illustrates the comprehensive workflow of Chost Hunter, from metric collection to AI analysis and safe resource right-sizing.

![Chost Hunter System Diagram](images/system_diagram.png)

### Detailed Workflow

1.  **Observability**: `cAdvisor` extracts real-time resource data from managed service containers.
2.  **Collection & Storage**: `Prometheus TSDB` scrapes metrics via Port 8080 and stores them as time-series data.
3.  **Visualization**: `Grafana Dashboard` visualizes the data, allowing operators to monitor the entire infrastructure at a glance.
4.  **AIOps Analysis**: The `AI Agent` fetches data via PromQL (Port 9090) and processes it through an LSTM model.
5.  **Recommendation**: The system converts predicted peak usage into CPU and memory limit recommendations with a safety buffer and minimum floors.
6.  **Policy & Notification**: Container labels and dashboard overrides decide whether the recommendation is advisory, automatically applied, or skipped. Important decisions can be sent to **Slack** via Webhook.
7.  **Safe Execution**: The `Executor` interacts with the **Docker Host Engine** to perform:
    * **Phase 1**: Register the previous limits with the watchdog for rollback.
    * **Phase 2**: Apply the recommended `cpu_quota` and `mem_limit` with `docker update`.

## 🛠️ Technology Stack

* **Infrastructure**: Linux / Docker Host Engine
* **Monitoring & Storage**: Prometheus, cAdvisor
* **Visualization**: Grafana
* **Analysis & Execution Agent**:
    * **Language**: Python 3.9+
    * **AI/ML**: Scikit-learn, PyTorch, Pandas
    * **Control**: Docker SDK for Python
* **Collaboration**: Slack (Outgoing Webhook)

## 🚀 Getting Started

You can deploy the monitoring stack (cAdvisor, Prometheus, Grafana, and Alertmanager) using `docker-compose`, then run the AI agent from the repository root.

```bash
# 1. Clone the repository
git clone [https://github.com/jagggged/chost-hunter.git](https://github.com/jagggged/chost-hunter.git)
cd chost-hunter

# 2. Launch the monitoring stack
docker-compose up -d

# 3. Run the AI agent locally only when developing outside Docker
python -m ai.main
```

## Runtime Control Policy

The AI agent supports three container policies through Docker labels:

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
published GHCR agent image and pretrained inference mode:

```bash
curl -O https://raw.githubusercontent.com/jagggged/chost-hunter/develop/docker-compose.yml
docker compose up -d
```

For local image verification before publishing:

```bash
docker build -t chost-hunter-agent:local .
AI_AGENT_IMAGE=chost-hunter-agent:local docker compose up -d ai-agent
```

Recommendation output is conservatively capped after inference. By default,
finite container limits are not increased above their current value
(`MAX_LIMIT_INCREASE_RATIO=1.0`), and absolute caps prevent runaway predictions
from becoming huge Docker limits (`MAX_CPU_QUOTA=4.0`,
`MAX_MEMORY_BYTES=2147483648`).

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

## Control API

When `ENABLE_CONTROL_API = True`, the AI agent starts a local API on
`http://127.0.0.1:8000`.

Useful endpoints:

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/actions?limit=20
curl http://127.0.0.1:8000/api/actions/latest
curl http://127.0.0.1:8000/api/recommendations/latest
curl http://127.0.0.1:8000/api/containers
curl http://127.0.0.1:8000/api/state
curl -X POST http://127.0.0.1:8000/api/actions/<action_id>/apply
curl -X POST http://127.0.0.1:8000/api/containers/<container_name>/policy \
  -H "Content-Type: application/json" \
  -d "{\"policy\":\"advisory\"}"
curl -X POST http://127.0.0.1:8000/api/state/autopilot \
  -H "Content-Type: application/json" \
  -d "{\"enabled\":false}"
```

The dashboard should read from these endpoints instead of parsing
`logs/actions.jsonl` directly. The JSONL file remains the operator-visible audit
trail.

Dashboard policy changes are stored as runtime overrides in
`logs/policy_overrides.json`. Docker `skip` labels still win over dashboard
overrides, so explicitly skipped containers remain protected.

The dashboard's Auto Resource Optimization toggle is the global autopilot kill
switch stored in `logs/global_state.json`. When it is off, containers whose
effective policy is `auto` still produce recommendations, but the agent does not
run `docker update`.

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

Every notification attempt is also written to `logs/notifications.jsonl`. If no
webhook URL is configured, Chost Hunter records the notification as `disabled`
there, which makes local verification possible without a real Slack workspace.
