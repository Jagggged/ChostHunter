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
