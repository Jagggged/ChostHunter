const API_BASE = 'http://127.0.0.1:8000';

const COLORS = {
  green: '#73bf69',
  yellow: '#f2cc0c',
  red: '#e02f44',
  blue: '#5794f2',
  purple: '#b877d9',
  orange: '#ff9830',
  grid: 'rgba(204, 204, 220, 0.08)',
  text: '#8e99a4',
  textMain: '#c7d0d9'
};

const CHART_OPTIONS = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: {
      position: 'bottom',
      labels: {
        color: COLORS.textMain,
        boxWidth: 10,
        font: { size: 10 }
      }
    },
    tooltip: { mode: 'index', intersect: false }
  },
  scales: {
    x: { grid: { color: COLORS.grid }, ticks: { color: COLORS.text } },
    y: { grid: { color: COLORS.grid }, ticks: { color: COLORS.text } }
  },
  interaction: { mode: 'nearest', axis: 'x', intersect: false },
};

const labels = Array.from(
  { length: 12 },
  (_, i) => `${10 + Math.floor(i / 2)}:${(i % 2) * 30 === 0 ? '00' : '30'}`
);

const mockData = {
  cpu: [
    [0.01, 0.01, 0.01, 0.02, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01],
    [0.05, 0.06, 0.05, 0.04, 0.05, 0.06, 0.05, 0.04, 0.05, 0.06, 0.05, 0.05],
    [0.02, 0.02, 0.03, 0.02, 0.02, 0.02, 0.03, 0.02, 0.02, 0.02, 0.03, 0.02],
    [0.03, 0.03, 0.03, 0.04, 0.03, 0.03, 0.03, 0.04, 0.03, 0.03, 0.03, 0.03],
    [0.5, 0.6, 1.2, 1.5, 1.8, 2.0, 1.9, 2.1, 2.2, 2.0, 1.9, 2.1]
  ],
  mem: [
    [50, 50, 51, 50, 50, 50, 51, 50, 50, 50, 51, 50],
    [120, 121, 120, 120, 122, 121, 120, 120, 122, 121, 120, 120],
    [200, 205, 210, 208, 200, 205, 210, 208, 200, 205, 210, 208],
    [300, 305, 302, 300, 301, 305, 302, 300, 301, 305, 302, 300],
    [100, 150, 200, 250, 300, 350, 400, 450, 500, 510, 520, 530]
  ]
};

function getDataset(label, dataIndex, color, type) {
  return {
    label,
    data: mockData[type][dataIndex],
    borderColor: color,
    backgroundColor: `${color}33`,
    borderWidth: 2,
    pointRadius: 0,
    fill: type === 'mem'
  };
}

async function fetchJson(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || `Request failed: ${response.status}`);
  }
  return payload;
}

async function fetchJsonOptional(path, fallback) {
  try {
    return await fetchJson(path);
  } catch (error) {
    console.warn(`Optional API unavailable: ${path}`, error);
    return fallback;
  }
}

function formatBytes(bytes) {
  if (bytes == null) return '-';
  if (bytes === 0) return 'unlimited';
  const units = ['B', 'KB', 'MB', 'GB'];
  let value = Number(bytes);
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[unitIndex]}`;
}

function formatCpuQuota(cpuQuota) {
  if (cpuQuota == null) return '-';
  if (cpuQuota === 0) return 'unlimited';
  if (cpuQuota > 1000) return `${(cpuQuota / 100000).toFixed(2)} cores`;
  return `${Number(cpuQuota).toFixed(2)} cores`;
}

function formatTime(timestamp) {
  if (!timestamp) return '--:--';
  return new Date(timestamp).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit'
  });
}

function statusClass(status) {
  if (status === 'failed') return 'critical';
  if (status === 'applied') return 'optimal';
  return 'waste';
}

function displayReason(action) {
  const reason = action.reason || action.error || action.status;
  if (!reason) return action.status;
  if (reason.includes('No such container') || reason.includes('404 Client Error')) {
    return 'container does not exist';
  }
  return reason;
}

function limitLine(label, currentValue, targetValue, formatter, isApplied) {
  if (isApplied) {
    return `
      ${label} <span class="highlight-green">${formatter(currentValue)}</span>
      <span class="metric-note">applied</span>
    `;
  }
  return `
    ${label} <span class="highlight-red">${formatter(currentValue)}</span>
    &rarr; <span class="highlight-green">${formatter(targetValue)}</span>
  `;
}

function initCharts() {
  const ctxCpu = document.getElementById('chart-cpu').getContext('2d');
  new Chart(ctxCpu, {
    type: 'line',
    data: {
      labels,
      datasets: [
        getDataset('alertmanager', 0, COLORS.blue, 'cpu'),
        getDataset('cadvisor', 1, COLORS.green, 'cpu'),
        getDataset('grafana', 2, COLORS.orange, 'cpu'),
        getDataset('prometheus', 3, COLORS.purple, 'cpu'),
        getDataset('chost-test-auto', 4, COLORS.red, 'cpu')
      ]
    },
    options: CHART_OPTIONS
  });

  const ctxMem = document.getElementById('chart-mem').getContext('2d');
  new Chart(ctxMem, {
    type: 'line',
    data: {
      labels,
      datasets: [
        getDataset('alertmanager', 0, COLORS.blue, 'mem'),
        getDataset('cadvisor', 1, COLORS.green, 'mem'),
        getDataset('grafana', 2, COLORS.orange, 'mem'),
        getDataset('prometheus', 3, COLORS.purple, 'mem'),
        getDataset('chost-test-auto', 4, COLORS.red, 'mem')
      ]
    },
    options: CHART_OPTIONS
  });

  new Chart(document.getElementById('chart-rx').getContext('2d'), {
    type: 'line',
    data: { labels, datasets: [getDataset('cadvisor', 1, COLORS.green, 'cpu')] },
    options: CHART_OPTIONS
  });
  new Chart(document.getElementById('chart-tx').getContext('2d'), {
    type: 'line',
    data: { labels, datasets: [getDataset('prometheus', 3, COLORS.purple, 'cpu')] },
    options: CHART_OPTIONS
  });
}

function renderGauges(id, data) {
  const container = document.getElementById(id);
  container.innerHTML = data.map(item => `
    <div class="gauge-row">
      <div class="gauge-label">
        <span>${item.name}</span>
        <span class="gauge-val" style="color: ${item.color}">${item.val}% (${item.text})</span>
      </div>
      <div class="gauge-bar-bg">
        <div class="gauge-fill" style="width: ${item.val}%; background-color: ${item.color};"></div>
      </div>
    </div>
  `).join('');
}

function initGauges() {
  renderGauges('bar-cpu', [
    { name: 'chost-test-auto', val: 25, text: '0.25 cores', color: COLORS.yellow },
    { name: 'cadvisor', val: 5, text: '0.05 cores', color: COLORS.green },
    { name: 'prometheus', val: 3, text: '0.03 cores', color: COLORS.green },
    { name: 'grafana', val: 2, text: '0.02 cores', color: COLORS.green },
    { name: 'alertmanager', val: 1, text: '0.01 cores', color: COLORS.green }
  ]);

  renderGauges('bar-mem', [
    { name: 'chost-test-auto', val: 25, text: '128 MB', color: COLORS.yellow },
    { name: 'prometheus', val: 45, text: '300 MB', color: COLORS.yellow },
    { name: 'grafana', val: 32, text: '208 MB', color: COLORS.yellow },
    { name: 'cadvisor', val: 18, text: '120 MB', color: COLORS.green },
    { name: 'alertmanager', val: 8, text: '50 MB', color: COLORS.green }
  ]);
}

async function applyAction(actionId) {
  const button = document.querySelector(`[data-action-id="${actionId}"]`);
  if (button) {
    button.disabled = true;
    button.textContent = 'Applying';
  }
  try {
    await fetchJson(`/api/actions/${actionId}/apply`, { method: 'POST' });
    await refreshRuntimePanels();
  } catch (error) {
    if (button) {
      button.disabled = false;
      button.textContent = 'Apply';
    }
    console.error(error);
  }
}

async function setContainerPolicy(containerName, policy) {
  await fetchJson(`/api/containers/${encodeURIComponent(containerName)}/policy`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ policy })
  });
  await refreshRuntimePanels();
}

async function setAutopilot(enabled) {
  await fetchJson('/api/state/autopilot', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled })
  });
  await refreshRuntimePanels();
}

async function setFinetune(enabled) {
  await fetchJson('/api/state/finetune', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled })
  });
  await refreshRuntimePanels();
}

async function saveFinetuneSettings() {
  const button = document.getElementById('finetune-save-btn');
  const feedback = document.getElementById('finetune-feedback');
  const payload = {
    interval_sec: Number(document.getElementById('finetune-interval').value),
    initial_delay_sec: Number(document.getElementById('finetune-initial-delay').value),
    history_sec: Number(document.getElementById('finetune-history').value),
    max_containers: Number(document.getElementById('finetune-max-containers').value),
    skip_cpu_threshold: Number(document.getElementById('finetune-cpu-skip').value),
    skip_memory_threshold: Number(document.getElementById('finetune-memory-skip').value),
    target_containers: document.getElementById('finetune-targets').value,
    auto_promote: document.getElementById('finetune-auto-promote').checked
  };

  button.disabled = true;
  feedback.className = 'feedback-line';
  feedback.textContent = 'Saving';
  try {
    const response = await fetchJson('/api/settings/finetune', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    renderFinetuneSettings(response.settings || {});
    feedback.className = 'feedback-line ok';
    feedback.textContent = 'Saved';
    await refreshRuntimePanels();
  } catch (error) {
    feedback.className = 'feedback-line error';
    feedback.textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

async function saveSlackSettings() {
  const input = document.getElementById('slack-webhook-input');
  const toggle = document.getElementById('toggle-slack');
  const button = document.getElementById('slack-save-btn');
  const feedback = document.getElementById('slack-feedback');
  const payload = { enabled: toggle.checked };
  const webhookUrl = input.value.trim();
  if (webhookUrl) {
    payload.webhook_url = webhookUrl;
  }

  button.disabled = true;
  feedback.className = 'feedback-line';
  feedback.textContent = 'Saving';
  try {
    const response = await fetchJson('/api/settings/notifications/slack', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    input.value = '';
    renderSlackSettings(response.slack || {});
    feedback.className = 'feedback-line ok';
    feedback.textContent = 'Saved';
    await refreshRuntimePanels();
  } catch (error) {
    feedback.className = 'feedback-line error';
    feedback.textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

async function testSlackSettings() {
  const button = document.getElementById('slack-test-btn');
  const feedback = document.getElementById('slack-feedback');
  button.disabled = true;
  feedback.className = 'feedback-line';
  feedback.textContent = 'Sending test';
  try {
    await fetchJson('/api/settings/notifications/slack/test', { method: 'POST' });
    feedback.className = 'feedback-line ok';
    feedback.textContent = 'Test sent';
    await refreshRuntimePanels();
  } catch (error) {
    feedback.className = 'feedback-line error';
    feedback.textContent = error.message;
    await refreshRuntimePanels();
  } finally {
    button.disabled = false;
  }
}

function policySelectMarkup(containerName, policy) {
  const policies = ['auto', 'advisory', 'skip'];
  return `
    <select class="policy-select" data-policy-container="${containerName}">
      ${policies.map(option => `
        <option value="${option}" ${option === policy ? 'selected' : ''}>${option}</option>
      `).join('')}
    </select>
  `;
}

function recommendationMarkup(item, containerState) {
  const current = containerState?.limits || item.current_limits || {};
  const recommended = item.recommended_limits || {};
  const applied = item.applied_limits || recommended;
  const badgeClass = statusClass(item.status);
  const canApply = Boolean(containerState) && item.status === 'recommended' && recommended.cpu_quota != null;
  const isApplied = item.status === 'applied';
  const effectivePolicy = containerState?.policy || item.policy;
  const policySource = containerState?.policy_source || item.policy;
  const missingContainer = !containerState;

  return `
    <div class="waste-item">
      <div class="waste-item-header">
        <span class="container-name">${item.container}</span>
        <span class="status-badge ${badgeClass}">${item.status.toUpperCase()}</span>
      </div>
      <div class="waste-metrics-grid">
        <div class="waste-metric">
          <div class="waste-details">
            ${limitLine('CPU', current.cpu_quota, applied.cpu_quota, formatCpuQuota, isApplied)}
          </div>
        </div>
        <div class="waste-metric">
          <div class="waste-details">
            ${limitLine('Memory', current.memory_bytes, applied.memory_bytes, formatBytes, isApplied)}
          </div>
        </div>
      </div>
      <div class="action-row">
        <span>${missingContainer ? 'container not found' : `${policySource} policy`}</span>
        ${missingContainer ? '' : policySelectMarkup(item.container, effectivePolicy)}
        ${canApply ? `<button class="action-btn" data-action-id="${item.id}">Apply</button>` : ''}
      </div>
    </div>
  `;
}

function renderRecommendations(items, containers) {
  const container = document.getElementById('waste-list');
  if (!items.length) {
    container.innerHTML = '<div class="empty-state">No recommendations yet.</div>';
    return;
  }
  const containersByName = new Map(containers.map(item => [item.name, item]));
  container.innerHTML = items
    .map(item => recommendationMarkup(item, containersByName.get(item.container)))
    .join('');
  container.querySelectorAll('[data-action-id]').forEach(button => {
    button.addEventListener('click', () => applyAction(button.dataset.actionId));
  });
  container.querySelectorAll('[data-policy-container]').forEach(select => {
    select.addEventListener('change', () => {
      setContainerPolicy(select.dataset.policyContainer, select.value).catch(error => {
        console.error(error);
        refreshRuntimePanels();
      });
    });
  });
}

function renderHistory(actions) {
  const list = document.getElementById('history-list');
  if (!actions.length) {
    list.innerHTML = '<li>No action history yet.</li>';
    return;
  }

  list.innerHTML = actions.map(action => {
    const badgeClass = action.status === 'failed' ? 'warning' : 'info';
    const reason = displayReason(action);
    return `
      <li>
        <span class="time">${formatTime(action.timestamp)}</span>
        <span class="badge ${badgeClass}">${action.container}</span>
        <span class="highlight">${action.status}</span>
        <span>${reason}</span>
      </li>
    `;
  }).join('');
}

function updateSummary(actions, recommendations) {
  const amount = document.querySelector('.savings-amount');
  const appliedCount = actions.filter(action => action.status === 'applied').length;
  const recommendationCount = recommendations.length;
  amount.innerHTML = `${appliedCount}<span> applied / ${recommendationCount} current</span>`;
}

function renderAutopilotState(state) {
  const toggle = document.getElementById('toggle-optimization');
  const labelObj = document.getElementById('optimization-label');
  const descObj = document.getElementById('optimization-desc');
  const intervalBlock = document.getElementById('interval-setting');
  const intervalSelect = document.getElementById('interval-select');
  const enabled = Boolean(state.autopilot_enabled);

  toggle.checked = enabled;
  if (enabled) {
    labelObj.className = 'label-on';
    labelObj.innerText = 'Status: Active';
    descObj.innerText = `Auto policy can apply changes. Refresh every ${intervalSelect.value} minutes.`;
    intervalBlock.classList.remove('disabled');
    intervalSelect.disabled = false;
  } else {
    labelObj.className = 'label-off';
    labelObj.innerText = 'Status: Advisory';
    descObj.innerText = 'Global autopilot is off. Auto containers show recommendations only.';
    intervalBlock.classList.add('disabled');
    intervalSelect.disabled = true;
  }
}

function renderSlackSettings(slack) {
  const toggle = document.getElementById('toggle-slack');
  const label = document.getElementById('slack-label');
  const desc = document.getElementById('slack-desc');
  const input = document.getElementById('slack-webhook-input');
  const testButton = document.getElementById('slack-test-btn');
  const configured = Boolean(slack.configured);
  const enabled = Boolean(slack.enabled);

  toggle.checked = enabled;
  testButton.disabled = !configured || !enabled;
  if (configured && enabled) {
    label.className = 'label-on';
    label.textContent = 'Slack: Connected';
  } else if (configured) {
    label.className = 'label-off';
    label.textContent = 'Slack: Paused';
  } else {
    label.className = 'label-off';
    label.textContent = 'Slack: Not Connected';
  }

  const source = slack.source && slack.source !== 'none' ? ` (${slack.source})` : '';
  desc.textContent = configured
    ? `${slack.webhook_url_masked}${source}`
    : 'No webhook configured.';
  input.placeholder = configured ? 'Replace Slack webhook URL' : 'Slack webhook URL';
}

function renderFinetuneState(state, latestRun) {
  const toggle = document.getElementById('toggle-finetune');
  const label = document.getElementById('finetune-label');
  const desc = document.getElementById('finetune-desc');
  const latest = document.getElementById('finetune-latest');
  const enabled = Boolean(state.finetune_enabled);

  toggle.checked = enabled;
  if (enabled) {
    label.className = 'label-on';
    label.textContent = 'Fine-tuning: On';
    desc.textContent = 'Scheduler can train candidate runtime models.';
  } else {
    label.className = 'label-off';
    label.textContent = 'Fine-tuning: Off';
    desc.textContent = 'Pretrained inference only.';
  }

  if (!latestRun) {
    latest.textContent = 'Latest run: none';
    return;
  }
  const status = latestRun.status || 'unknown';
  const reason = latestRun.reason ? ` - ${latestRun.reason}` : '';
  const samples = latestRun.samples != null ? ` (${latestRun.samples} samples)` : '';
  latest.textContent = `Latest run: ${status}${samples}${reason}`;
}

function renderFinetuneSettings(settings) {
  if (!settings || !Object.keys(settings).length) return;
  document.getElementById('finetune-interval').value = settings.interval_sec ?? '';
  document.getElementById('finetune-initial-delay').value = settings.initial_delay_sec ?? '';
  document.getElementById('finetune-history').value = settings.history_sec ?? '';
  document.getElementById('finetune-max-containers').value = settings.max_containers ?? '';
  document.getElementById('finetune-cpu-skip').value = settings.skip_cpu_threshold ?? '';
  document.getElementById('finetune-memory-skip').value = settings.skip_memory_threshold ?? '';
  document.getElementById('finetune-targets').value = (settings.target_containers || []).join(', ');
  document.getElementById('finetune-auto-promote').checked = Boolean(settings.auto_promote);
}

async function refreshRuntimePanels() {
  try {
    const [
      actionsPayload,
      recommendationsPayload,
      containersPayload,
      statePayload,
      settingsPayload,
      finetunePayload,
      finetuneSettingsPayload
    ] = await Promise.all([
      fetchJson('/api/actions?limit=12'),
      fetchJson('/api/recommendations/latest'),
      fetchJson('/api/containers'),
      fetchJson('/api/state'),
      fetchJsonOptional('/api/settings/notifications', {
        slack: {
          enabled: false,
          configured: false,
          source: 'none',
          webhook_url_masked: ''
        }
      }),
      fetchJsonOptional('/api/finetune/latest', { run: null }),
      fetchJsonOptional('/api/settings/finetune', { settings: null })
    ]);
    const actions = actionsPayload.actions || [];
    const recommendations = recommendationsPayload.recommendations || [];
    const containers = containersPayload.containers || [];
    renderRecommendations(recommendations, containers);
    renderHistory(actions);
    updateSummary(actions, recommendations);
    renderAutopilotState(statePayload.state || {});
    renderSlackSettings((settingsPayload || {}).slack || {});
    renderFinetuneState(statePayload.state || {}, (finetunePayload || {}).run);
    renderFinetuneSettings((finetuneSettingsPayload || {}).settings || {});
  } catch (error) {
    document.getElementById('waste-list').innerHTML = `
      <div class="empty-state">
        Control API is not reachable at ${API_BASE}.
      </div>
    `;
    renderHistory([]);
    console.error(error);
  }
}

function setupToggle() {
  const toggle = document.getElementById('toggle-optimization');
  const labelObj = document.getElementById('optimization-label');
  const descObj = document.getElementById('optimization-desc');
  const intervalBlock = document.getElementById('interval-setting');
  const intervalSelect = document.getElementById('interval-select');

  toggle.addEventListener('change', event => {
    const enabled = event.target.checked;
    toggle.disabled = true;
    setAutopilot(enabled).finally(() => {
      toggle.disabled = false;
    });
  });

  intervalSelect.addEventListener('change', event => {
    if (toggle.checked) {
      descObj.innerText = `Auto policy active. Refresh every ${event.target.value} minutes.`;
    }
  });
}

function setupSlackSettings() {
  const saveButton = document.getElementById('slack-save-btn');
  const testButton = document.getElementById('slack-test-btn');
  const toggle = document.getElementById('toggle-slack');

  saveButton.addEventListener('click', saveSlackSettings);
  testButton.addEventListener('click', testSlackSettings);
  toggle.addEventListener('change', saveSlackSettings);
}

function setupFinetuneToggle() {
  const toggle = document.getElementById('toggle-finetune');
  const saveButton = document.getElementById('finetune-save-btn');
  toggle.addEventListener('change', event => {
    const enabled = event.target.checked;
    toggle.disabled = true;
    setFinetune(enabled).finally(() => {
      toggle.disabled = false;
    });
  });
  saveButton.addEventListener('click', saveFinetuneSettings);
}

window.onload = () => {
  initCharts();
  initGauges();
  setupToggle();
  setupSlackSettings();
  setupFinetuneToggle();
  refreshRuntimePanels();
  document.querySelector('.btn-refresh').addEventListener('click', refreshRuntimePanels);
};
