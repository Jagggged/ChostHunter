# 👻 Chost Hunter

> **C**ontainer + **Ghost** Hunter: An AI-driven Zombie Container Detection & Automated Lifecycle Management System.

**Chost Hunter** is an AIOps-based resource optimization solution designed to intelligently detect **"Ghost Containers"**—idle resources that consume infrastructure costs without providing value—and perform secure automated reclamation through a snapshot-first workflow.

## 🌟 Key Features

* **🔍 AI-Powered Detection**: Goes beyond static thresholds by utilizing **Isolation Forest** or **LSTM** models to analyze time-series metric patterns for precise anomaly (zombie) detection.
* **🛡️ Safety First (Snapshot)**: Before terminating an idle container, the system executes a `docker commit` to archive the current state as a `.tar` image, ensuring 0% data loss and instant rollback capability.
* **🤖 Automated Lifecycle**: A seamless end-to-end pipeline: Monitoring ⮕ Detection ⮕ Alerting ⮕ Approval ⮕ Recovery.
* **Standard Tech Stack**: Built on industry-standard open-source tools including cAdvisor, Prometheus, Grafana, and Docker SDK for high reliability and portability.

## 🏗️ System Architecture

This diagram illustrates the comprehensive workflow of Chost Hunter, from metric collection to AI analysis and secure resource reclamation.

![Chost Hunter System Diagram](images/system_diagram.png)

### Detailed Workflow

1.  **Observability**: `cAdvisor` extracts real-time resource data from managed service containers.
2.  **Collection & Storage**: `Prometheus TSDB` scrapes metrics via Port 8080 and stores them as time-series data.
3.  **Visualization**: `Grafana Dashboard` visualizes the data, allowing operators to monitor the entire infrastructure at a glance.
4.  **AIOps Analysis**: The `AI Agent` fetches data via PromQL (Port 9090) and processes it through ML models (Isolation Forest/LSTM).
5.  **Decision**: The system determines if a container is a "Zombie" based on learned patterns.
6.  **Alert & Human-in-the-loop**: If a zombie is detected, the `Alert Controller` sends a notification to **Slack** via Webhook. The operator provides final approval or an extension.
7.  **Safe Execution**: The `Executor` interacts with the **Docker Host Engine** via Unix Socket to perform:
    * **Phase 1**: Create a snapshot image (`.tar`) and store it in `Snapshot Storage`.
    * **Phase 2**: Stop the target container once the snapshot is verified.

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

You can deploy the entire Chost Hunter stack (cAdvisor, Prometheus, Grafana, and the Agent) using `docker-compose`.

```bash
# 1. Clone the repository
git clone [https://github.com/jagggged/chost-hunter.git](https://github.com/jagggged/chost-hunter.git)
cd chost-hunter

# 2. Configure environment variables
cp .env.example .env
# Edit .env with your Slack tokens and credentials

# 3. Launch the system
docker-compose up -d
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
