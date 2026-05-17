System.register(["@grafana/data", "react"], function (exports) {
  "use strict";

  var PanelPlugin, React;
  var DEFAULT_API_BASE = "http://127.0.0.1:8000";

  function apiFetch(apiBase, path, options) {
    return fetch(apiBase.replace(/\/$/, "") + path, options || {}).then(function (response) {
      return response.json().then(function (payload) {
        if (!response.ok) {
          throw new Error(payload.error || "Request failed: " + response.status);
        }
        return payload;
      });
    });
  }

  function optionalFetch(apiBase, path, fallback) {
    return apiFetch(apiBase, path).catch(function () {
      return fallback;
    });
  }

  function formatBytes(bytes) {
    if (bytes == null) {
      return "-";
    }
    if (bytes === 0) {
      return "unlimited";
    }
    var units = ["B", "KB", "MB", "GB"];
    var value = Number(bytes);
    var unitIndex = 0;
    while (value >= 1024 && unitIndex < units.length - 1) {
      value = value / 1024;
      unitIndex += 1;
    }
    return value.toFixed(value >= 10 ? 0 : 1) + " " + units[unitIndex];
  }

  function formatCpu(cpuQuota) {
    if (cpuQuota == null) {
      return "-";
    }
    if (cpuQuota === 0) {
      return "unlimited";
    }
    if (cpuQuota > 1000) {
      return (cpuQuota / 100000).toFixed(2) + " cores";
    }
    return Number(cpuQuota).toFixed(2) + " cores";
  }

  function formatTime(timestamp) {
    if (!timestamp) {
      return "--:--";
    }
    return new Date(timestamp).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function statusColor(status) {
    if (status === "applied" || status === "rolled_back" || status === "promoted") {
      return "#73bf69";
    }
    if (status === "failed" || status === "rollback_failed" || status === "rejected") {
      return "#e02f44";
    }
    if (status === "recommended" || status === "validated") {
      return "#f2cc0c";
    }
    return "#8e99a4";
  }

  function statusLabel(status) {
    var labels = {
      applied: "적용됨",
      recommended: "권고",
      skipped: "건너뜀",
      failed: "실패",
      rolled_back: "롤백됨",
      rollback_failed: "롤백 실패",
      promoted: "승격됨",
      rejected: "거절됨",
      validated: "검증됨",
      settings_updated: "설정 변경",
      notification_test: "알림 테스트",
      finetune_updated: "파인튜닝 전환",
      finetune_settings_updated: "파인튜닝 설정",
      autopilot_updated: "오토파일럿 전환",
      policy_updated: "정책 변경",
    };
    return labels[status] || status || "-";
  }

  function recommendationStatusLabel(item) {
    if ((item.reason || "").indexOf("already applied") >= 0) {
      return "이미 적용됨";
    }
    if (item.status === "recommended" && item.policy === "auto") {
      return "자동 확인";
    }
    return statusLabel(item.status);
  }

  function recommendationDetail(item, container) {
    if ((item.reason || "").indexOf("already applied") >= 0) {
      return "권고값이 현재 limit와 같아서 추가 적용하지 않았습니다.";
    }
    if (item.status === "applied") {
      return "자동 정책에 따라 Docker limit에 반영됐습니다.";
    }
    if (container && container.policy === "advisory") {
      return "권고만 생성하고 실제 limit은 바꾸지 않습니다.";
    }
    if (item.status === "recommended") {
      return item.reason || "수동 적용이 필요한 권고입니다.";
    }
    return item.reason || item.error || "";
  }

  function policyLabel(policy) {
    var labels = {
      auto: "자동 적용",
      advisory: "권고만",
      skip: "제외",
      global: "전체",
      notification: "알림",
    };
    return labels[policy] || policy || "-";
  }

  function policyOptionLabel(policy) {
    var labels = {
      auto: "자동",
      advisory: "권고",
      skip: "제외",
    };
    return labels[policy] || policy || "-";
  }

  function policySourceLabel(source) {
    var labels = {
      override: "화면에서 변경됨",
      "label-or-default": "라벨 또는 기본값",
    };
    return labels[source] || source || "라벨 또는 기본값";
  }

  function compactSeconds(seconds) {
    var value = Number(seconds || 0);
    if (!value) {
      return "0초";
    }
    if (value % 3600 === 0) {
      return value / 3600 + "시간";
    }
    if (value % 60 === 0) {
      return value / 60 + "분";
    }
    return value + "초";
  }

  function toggle(apiBase, path, enabled, refresh, setBusy) {
    setBusy(true);
    apiFetch(apiBase, path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: enabled }),
    }).then(refresh).finally(function () {
      setBusy(false);
    });
  }

  function setPolicy(apiBase, containerName, policy, refresh) {
    apiFetch(apiBase, "/api/containers/" + encodeURIComponent(containerName) + "/policy", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ policy: policy }),
    }).then(refresh);
  }

  function applyAction(apiBase, actionId, refresh, setBusy) {
    setBusy(true);
    apiFetch(apiBase, "/api/actions/" + actionId + "/apply", { method: "POST" })
      .then(refresh)
      .finally(function () {
        setBusy(false);
      });
  }

  function saveFinetune(apiBase, settings, refresh, setBusy, onSuccess, onError) {
    setBusy(true);
    apiFetch(apiBase, "/api/settings/finetune", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings),
    }).then(function (payload) {
      return refresh().then(function () {
        if (onSuccess) {
          onSuccess(payload.settings || {});
        }
      });
    }).catch(function (error) {
      if (onError) {
        onError(error.message);
      }
    }).finally(function () {
      setBusy(false);
    });
  }

  function saveSlack(apiBase, enabled, webhook, refresh, setBusy) {
    var payload = { enabled: enabled };
    if (webhook) {
      payload.webhook_url = webhook;
    }
    setBusy(true);
    apiFetch(apiBase, "/api/settings/notifications/slack", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then(refresh).finally(function () {
      setBusy(false);
    });
  }

  function testSlack(apiBase, refresh, setBusy) {
    setBusy(true);
    apiFetch(apiBase, "/api/settings/notifications/slack/test", {
      method: "POST",
    }).then(refresh).finally(function () {
      setBusy(false);
    });
  }

  function displayContainerName(name) {
    if (name === "__finetune__") {
      return "파인튜닝";
    }
    if (name === "__notifications__") {
      return "알림 설정";
    }
    if (name === "__global__") {
      return "전체 설정";
    }
    return name || "-";
  }

  function ChostHunterPanel(props) {
    var apiBase = props.options.apiBase || DEFAULT_API_BASE;
    var stateTuple = React.useState({
      loading: true,
      error: "",
      actions: [],
      recommendations: [],
      containers: [],
      state: {},
      finetuneRun: null,
      finetuneSettings: {},
      slack: {},
    });
    var data = stateTuple[0];
    var setData = stateTuple[1];
    var busyTuple = React.useState(false);
    var busy = busyTuple[0];
    var setBusy = busyTuple[1];
    var webhookTuple = React.useState("");
    var webhook = webhookTuple[0];
    var setWebhook = webhookTuple[1];

    var refresh = React.useCallback(function () {
      setData(function (current) {
        return Object.assign({}, current, { loading: true, error: "" });
      });
      return Promise.all([
        apiFetch(apiBase, "/api/actions?limit=8"),
        apiFetch(apiBase, "/api/recommendations/latest"),
        apiFetch(apiBase, "/api/containers"),
        apiFetch(apiBase, "/api/state"),
        optionalFetch(apiBase, "/api/finetune/latest", { run: null }),
        optionalFetch(apiBase, "/api/settings/finetune", { settings: {} }),
        optionalFetch(apiBase, "/api/settings/notifications", { slack: {} }),
      ]).then(function (responses) {
        setData({
          loading: false,
          error: "",
          actions: responses[0].actions || [],
          recommendations: responses[1].recommendations || [],
          containers: responses[2].containers || [],
          state: responses[3].state || {},
          finetuneRun: responses[4].run || null,
          finetuneSettings: responses[5].settings || {},
          slack: responses[6].slack || {},
        });
      }).catch(function (error) {
        setData(function (current) {
          return Object.assign({}, current, { loading: false, error: error.message });
        });
      });
    }, [apiBase]);

    React.useEffect(function () {
      refresh();
      var timer = setInterval(refresh, 10000);
      return function () {
        clearInterval(timer);
      };
    }, [refresh]);

    return React.createElement(
      "div",
      { style: styles.shell },
      React.createElement(Header, { loading: data.loading, busy: busy, refresh: refresh }),
      data.error ? React.createElement("div", { style: styles.error }, data.error) : null,
      React.createElement(RuntimeSummary, { data: data }),
      React.createElement(RecommendationList, {
        apiBase: apiBase,
        data: data,
        refresh: refresh,
        setBusy: setBusy,
      }),
      React.createElement(ControlSection, {
        apiBase: apiBase,
        data: data,
        refresh: refresh,
        busy: busy,
        setBusy: setBusy,
      }),
      React.createElement(ManagedPolicies, {
        apiBase: apiBase,
        data: data,
        refresh: refresh,
      }),
      React.createElement(FinetuneSection, {
        apiBase: apiBase,
        data: data,
        refresh: refresh,
        busy: busy,
        setBusy: setBusy,
      }),
      React.createElement(SlackSection, {
        apiBase: apiBase,
        data: data,
        refresh: refresh,
        busy: busy,
        setBusy: setBusy,
        webhook: webhook,
        setWebhook: setWebhook,
      }),
      React.createElement(ActionHistory, { actions: data.actions })
    );
  }

  function Header(props) {
    return React.createElement(
      "div",
      { style: styles.header },
      React.createElement("div", null,
        React.createElement("div", { style: styles.title }, "Chost Hunter"),
        React.createElement("div", { style: styles.muted }, "AI 권고와 런타임 제어")
      ),
      React.createElement(
        "button",
        { style: styles.iconButton, onClick: props.refresh, disabled: props.loading || props.busy },
        props.loading ? "..." : "새로고침"
      )
    );
  }

  function RuntimeSummary(props) {
    var applied = props.data.actions.filter(function (action) { return action.status === "applied"; }).length;
    var rollback = props.data.actions.filter(function (action) { return action.status === "rolled_back"; }).length;
    var latest = props.data.actions[0];
    return React.createElement(
      "div",
      { style: styles.stats },
      React.createElement(Stat, { label: "적용", value: String(applied) }),
      React.createElement(Stat, { label: "최근 판단", value: String(props.data.recommendations.length) }),
      React.createElement(Stat, { label: "롤백", value: String(rollback) }),
      React.createElement(Stat, { label: "최근 상태", value: latest ? statusLabel(latest.status) : "-" })
    );
  }

  function Stat(props) {
    return React.createElement(
      "div",
      { style: styles.stat },
      React.createElement("div", { style: styles.statValue }, props.value),
      React.createElement("div", { style: styles.statLabel }, props.label)
    );
  }

  function RecommendationList(props) {
    var containers = {};
    props.data.containers.forEach(function (container) {
      containers[container.name] = container;
    });
    return React.createElement(
      "section",
      { style: styles.section },
      React.createElement("div", { style: styles.sectionTitle }, "최근 AI 판단"),
      props.data.recommendations.length === 0
        ? React.createElement("div", { style: styles.empty }, "아직 AI 판단 기록이 없습니다.")
        : props.data.recommendations.map(function (item) {
            return React.createElement(RecommendationRow, {
              key: item.id || item.container,
              apiBase: props.apiBase,
              item: item,
              container: containers[item.container],
              refresh: props.refresh,
              setBusy: props.setBusy,
            });
          })
    );
  }

  function RecommendationRow(props) {
    var item = props.item;
    var container = props.container;
    var current = (container && container.limits) || item.current_limits || {};
    var recommended = item.recommended_limits || {};
    var effectivePolicy = (container && container.policy) || item.policy;
    var alreadyApplied = (item.reason || "").indexOf("already applied") >= 0;
    var canApply = Boolean(container)
      && item.status === "recommended"
      && effectivePolicy !== "auto"
      && !alreadyApplied
      && recommended.cpu_quota != null;
    var detail = recommendationDetail(item, container);
    return React.createElement(
      "div",
      { style: styles.recommendation },
      React.createElement(
        "div",
        { style: styles.rowBetween },
        React.createElement("strong", { style: styles.containerName }, item.container),
        React.createElement("span", { style: badgeStyle(item.status) }, recommendationStatusLabel(item))
      ),
      React.createElement(
        "div",
        { style: styles.limitGrid },
        React.createElement("span", null, "CPU ", formatCpu(current.cpu_quota), " -> ", formatCpu(recommended.cpu_quota)),
        React.createElement("span", null, "메모리 ", formatBytes(current.memory_bytes), " -> ", formatBytes(recommended.memory_bytes))
      ),
      detail ? React.createElement("div", { style: styles.recommendationNote }, detail) : null,
      React.createElement(
        "div",
        { style: styles.recommendationControls },
        canApply
          ? React.createElement(
              "button",
              {
                style: styles.applyButton,
                onClick: function () {
                  applyAction(props.apiBase, item.id, props.refresh, props.setBusy);
                },
              },
              "적용"
            )
          : React.createElement("span", { style: styles.muted }, "자동/이미 적용된 판단입니다. 정책 변경은 아래에서 합니다.")
      )
    );
  }

  function ControlSection(props) {
    var autopilot = Boolean(props.data.state.autopilot_enabled);
    return React.createElement(
      "section",
      { style: styles.section },
      React.createElement("div", { style: styles.sectionTitle }, "런타임 제어"),
      React.createElement(ToggleLine, {
        label: "오토파일럿",
        detail: autopilot ? "자동 정책은 실제 Docker limit을 변경할 수 있습니다." : "권고만 만들고 실제 적용은 하지 않습니다.",
        checked: autopilot,
        disabled: props.busy,
        onChange: function (checked) {
          toggle(props.apiBase, "/api/state/autopilot", checked, props.refresh, props.setBusy);
        },
      })
    );
  }

  function ManagedPolicies(props) {
    var containers = props.data.containers || [];
    return React.createElement(
      "section",
      { style: styles.section },
      React.createElement("div", { style: styles.sectionTitle }, "컨테이너 정책"),
      React.createElement(
        "div",
        { style: styles.policyLegend },
        ["auto", "advisory", "skip"].map(function (policy) {
          return React.createElement("span", { key: policy, style: policyBadgeStyle(policy) }, policyLabel(policy));
        })
      ),
      containers.length === 0
        ? React.createElement("div", { style: styles.empty }, "관리 대상 워크로드 컨테이너가 없습니다. auto/advisory/skip을 보려면 라벨이 붙은 데모 컨테이너를 실행하세요.")
        : containers.map(function (container) {
            return React.createElement(
              "div",
              { key: container.name, style: styles.policyRow },
              React.createElement(
                "div",
                { style: styles.policyName },
                React.createElement("strong", null, container.name),
                React.createElement("span", { style: styles.muted }, policySourceLabel(container.policy_source))
              ),
              React.createElement(
                "select",
                {
                  style: styles.select,
                  value: container.policy || "auto",
                  onChange: function (event) {
                    setPolicy(props.apiBase, container.name, event.target.value, props.refresh);
                  },
                },
                ["auto", "advisory", "skip"].map(function (policy) {
                  return React.createElement("option", { key: policy, value: policy }, policyOptionLabel(policy));
                })
              )
            );
          })
    );
  }

  function FinetuneSection(props) {
    var enabled = Boolean(props.data.state.finetune_enabled);
    var settings = props.data.finetuneSettings || {};
    var run = props.data.finetuneRun;
    var draftTuple = React.useState(settings);
    var draft = draftTuple[0];
    var setDraft = draftTuple[1];
    var dirtyTuple = React.useState(false);
    var dirty = dirtyTuple[0];
    var setDirty = dirtyTuple[1];
    var messageTuple = React.useState("");
    var message = messageTuple[0];
    var setMessage = messageTuple[1];
    React.useEffect(function () {
      if (!dirty) {
        setDraft(settings);
      }
    }, [JSON.stringify(settings), dirty]);

    function updateDraft(key, value) {
      var next = {};
      next[key] = value;
      setDraft(Object.assign({}, draft, next));
      setDirty(true);
      setMessage("저장 전 변경사항이 있습니다.");
    }

    function normalizedDraft() {
      var integerKeys = ["interval_sec", "initial_delay_sec", "history_sec", "max_containers"];
      var next = Object.assign({}, draft);
      integerKeys.forEach(function (key) {
        if (next[key] !== "" && next[key] != null) {
          next[key] = Number(next[key]);
        }
      });
      return next;
    }

    return React.createElement(
      "section",
      { style: styles.section },
      React.createElement("div", { style: styles.sectionTitle }, "파인튜닝"),
      React.createElement(ToggleLine, {
        label: "자동 학습 스케줄러",
        detail: enabled ? "후보 모델 학습이 켜져 있습니다." : "프리트레인 모델 추론만 사용합니다.",
        checked: enabled,
        disabled: props.busy,
        onChange: function (checked) {
          toggle(props.apiBase, "/api/state/finetune", checked, props.refresh, props.setBusy);
        },
      }),
      React.createElement(
        "div",
        { style: styles.latest },
        "최근 실행: ",
        run ? statusLabel(run.status) + " (" + (run.samples || 0) + "개 샘플)" : "없음"
      ),
      React.createElement(
        "div",
        { style: styles.latest },
        "현재 주기: ",
        compactSeconds(settings.interval_sec),
        " / 최초 대기: ",
        compactSeconds(settings.initial_delay_sec),
        " / 데이터 기간: ",
        compactSeconds(settings.history_sec),
        " / 관리 대상: ",
        (props.data.containers || []).length,
        "개"
      ),
      React.createElement(
        "div",
        { style: styles.formGrid },
        NumberInput("학습 주기(초)", "interval_sec", draft, updateDraft),
        NumberInput("최초 대기(초)", "initial_delay_sec", draft, updateDraft),
        NumberInput("데이터 기간(초)", "history_sec", draft, updateDraft),
        NumberInput("학습 대상 최대 수", "max_containers", draft, updateDraft)
      ),
      React.createElement(
        "label",
        { style: styles.checkLine },
        React.createElement("input", {
          type: "checkbox",
          checked: Boolean(draft.auto_promote),
          onChange: function (event) {
            updateDraft("auto_promote", event.target.checked);
          },
        }),
        "검증 통과 모델 자동 적용"
      ),
      message ? React.createElement("div", { style: dirty ? styles.notice : styles.success }, message) : null,
      React.createElement(
        "button",
        {
          style: styles.button,
          disabled: props.busy || !dirty,
          onClick: function () {
            saveFinetune(
              props.apiBase,
              normalizedDraft(),
              props.refresh,
              props.setBusy,
              function (saved) {
                setDraft(saved);
                setDirty(false);
                setMessage("저장됨: 스케줄러는 다음 루프에서 새 설정으로 재시작됩니다.");
              },
              function (error) {
                setMessage("저장 실패: " + error);
              }
            );
          },
        },
        props.busy ? "저장 중..." : "파인튜닝 설정 저장"
      )
    );
  }

  function NumberInput(label, key, draft, updateDraft) {
    return React.createElement(
      "label",
      { style: styles.inputLabel, key: key },
      React.createElement("span", null, label),
      React.createElement("input", {
        style: styles.input,
        type: "number",
        value: draft[key] == null ? "" : draft[key],
        onChange: function (event) {
          updateDraft(key, event.target.value);
        },
      })
    );
  }

  function SlackSection(props) {
    var slack = props.data.slack || {};
    return React.createElement(
      "section",
      { style: styles.section },
      React.createElement("div", { style: styles.sectionTitle }, "Slack 알림"),
      React.createElement(ToggleLine, {
        label: slack.configured ? "연결됨" : "설정 안 됨",
        detail: slack.webhook_url_masked || "Webhook URL을 넣으면 Slack 알림을 보낼 수 있습니다.",
        checked: Boolean(slack.enabled),
        disabled: props.busy,
        onChange: function (checked) {
          saveSlack(props.apiBase, checked, "", props.refresh, props.setBusy);
        },
      }),
      React.createElement(
        "div",
        { style: styles.inlineForm },
        React.createElement("input", {
          style: styles.input,
          type: "password",
          placeholder: "Slack webhook URL",
          value: props.webhook,
          onChange: function (event) { props.setWebhook(event.target.value); },
        }),
        React.createElement(
          "button",
          {
            style: styles.button,
            disabled: props.busy,
            onClick: function () {
              saveSlack(props.apiBase, Boolean(slack.enabled), props.webhook, props.refresh, props.setBusy);
              props.setWebhook("");
            },
          },
          "저장"
        )
      ),
      React.createElement(
        "button",
        {
          style: Object.assign({}, styles.button, { marginTop: "6px" }),
          disabled: props.busy || !slack.enabled || !slack.configured,
          onClick: function () {
            testSlack(props.apiBase, props.refresh, props.setBusy);
          },
        },
        "테스트 알림 보내기"
      )
    );
  }

  function ToggleLine(props) {
    return React.createElement(
      "div",
      { style: styles.toggleLine },
      React.createElement("div", null,
        React.createElement("div", { style: styles.toggleTitle }, props.label),
        React.createElement("div", { style: styles.muted }, props.detail)
      ),
      React.createElement("input", {
        type: "checkbox",
        checked: props.checked,
        disabled: props.disabled,
        onChange: function (event) { props.onChange(event.target.checked); },
      })
    );
  }

  function ActionHistory(props) {
    return React.createElement(
      "section",
      { style: styles.section },
      React.createElement("div", { style: styles.sectionTitle }, "최근 작업"),
      props.actions.length === 0
        ? React.createElement("div", { style: styles.empty }, "아직 작업 기록이 없습니다.")
        : props.actions.map(function (action) {
            return React.createElement(
              "div",
              { key: action.id, style: styles.actionRow },
              React.createElement("span", { style: styles.time }, formatTime(action.timestamp)),
              React.createElement("span", { style: badgeStyle(action.status) }, statusLabel(action.status)),
              React.createElement("span", { style: styles.actionText }, displayContainerName(action.container))
            );
          })
    );
  }

  function badgeStyle(status) {
    return Object.assign({}, styles.badge, {
      color: statusColor(status),
      borderColor: statusColor(status),
      backgroundColor: statusColor(status) + "22",
    });
  }

  function policyBadgeStyle(policy) {
    var color = policy === "auto" ? "#73bf69" : policy === "advisory" ? "#f2cc0c" : "#8e99a4";
    return Object.assign({}, styles.badge, {
      color: color,
      borderColor: color,
      backgroundColor: color + "22",
    });
  }

  var styles = {
    shell: {
      height: "100%",
      overflow: "auto",
      overflowX: "hidden",
      padding: "8px",
      color: "#c7d0d9",
      fontFamily: "Inter, Arial, sans-serif",
      fontSize: "12px",
      background: "#111217",
    },
    header: {
      display: "flex",
      justifyContent: "space-between",
      alignItems: "center",
      gap: "8px",
      marginBottom: "10px",
    },
    title: { color: "#fff", fontSize: "15px", fontWeight: 700 },
    muted: { color: "#8e99a4", fontSize: "11px" },
    iconButton: {
      background: "#1f2327",
      border: "1px solid #2c3235",
      color: "#c7d0d9",
      borderRadius: "4px",
      padding: "5px 8px",
      cursor: "pointer",
    },
    stats: {
      display: "grid",
      gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
      gap: "6px",
      marginBottom: "8px",
    },
    stat: { border: "1px solid #2c3235", borderRadius: "4px", padding: "7px", background: "#181b1f" },
    statValue: { color: "#fff", fontSize: "15px", fontWeight: 700, overflow: "hidden", textOverflow: "ellipsis" },
    statLabel: { color: "#8e99a4", fontSize: "10px", marginTop: "2px" },
    section: { borderTop: "1px solid #2c3235", paddingTop: "9px", marginTop: "9px" },
    sectionTitle: { color: "#fff", fontWeight: 700, marginBottom: "7px", fontSize: "12px" },
    recommendation: {
      border: "1px solid #2c3235",
      borderRadius: "4px",
      padding: "8px",
      background: "#181b1f",
      marginBottom: "7px",
    },
    rowBetween: { display: "flex", justifyContent: "space-between", alignItems: "center", gap: "8px" },
    recommendationControls: {
      display: "grid",
      gridTemplateColumns: "minmax(0, 1fr)",
      gap: "8px",
      alignItems: "center",
      width: "100%",
    },
    containerName: { color: "#fff", minWidth: 0, overflow: "hidden", textOverflow: "ellipsis" },
    badge: { border: "1px solid", borderRadius: "4px", padding: "2px 5px", fontSize: "10px", whiteSpace: "nowrap" },
    limitGrid: { display: "grid", gridTemplateColumns: "1fr", gap: "3px", color: "#c7d0d9", margin: "7px 0" },
    recommendationNote: { color: "#8e99a4", fontSize: "11px", marginBottom: "7px", lineHeight: 1.35 },
    button: {
      background: "rgba(87,148,242,0.16)",
      border: "1px solid rgba(87,148,242,0.45)",
      color: "#dbeafe",
      borderRadius: "4px",
      padding: "5px 8px",
      cursor: "pointer",
      fontSize: "11px",
    },
    applyButton: {
      background: "rgba(87,148,242,0.16)",
      border: "1px solid rgba(87,148,242,0.45)",
      color: "#dbeafe",
      borderRadius: "4px",
      padding: "5px 10px",
      cursor: "pointer",
      fontSize: "11px",
      whiteSpace: "nowrap",
      width: "100%",
      minWidth: 0,
      boxSizing: "border-box",
    },
    select: {
      width: "100%",
      maxWidth: "100%",
      minWidth: 0,
      boxSizing: "border-box",
      background: "#111217",
      color: "#c7d0d9",
      border: "1px solid #2c3235",
      borderRadius: "4px",
      padding: "4px",
      fontSize: "11px",
    },
    policyLegend: { display: "flex", gap: "6px", marginBottom: "7px", flexWrap: "wrap" },
    policyRow: {
      display: "grid",
      gridTemplateColumns: "minmax(0, 1fr) minmax(72px, 84px)",
      gap: "8px",
      alignItems: "center",
      border: "1px solid #2c3235",
      borderRadius: "4px",
      padding: "7px",
      background: "#181b1f",
      marginBottom: "6px",
    },
    policyName: { display: "flex", flexDirection: "column", gap: "2px", minWidth: 0 },
    toggleLine: {
      display: "flex",
      justifyContent: "space-between",
      alignItems: "center",
      gap: "8px",
      marginBottom: "7px",
    },
    toggleTitle: { color: "#fff", fontWeight: 600 },
    latest: { color: "#8e99a4", fontSize: "11px", marginBottom: "7px" },
    formGrid: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px", marginBottom: "7px" },
    inputLabel: { display: "flex", flexDirection: "column", gap: "3px", color: "#8e99a4", fontSize: "10px" },
    input: {
      minWidth: 0,
      background: "#111217",
      color: "#c7d0d9",
      border: "1px solid #2c3235",
      borderRadius: "4px",
      padding: "5px 7px",
      fontSize: "11px",
    },
    checkLine: { display: "flex", alignItems: "center", gap: "6px", marginBottom: "7px" },
    inlineForm: { display: "grid", gridTemplateColumns: "1fr auto", gap: "6px" },
    actionRow: { display: "grid", gridTemplateColumns: "42px auto 1fr", gap: "6px", alignItems: "center", marginBottom: "5px" },
    time: { color: "#8e99a4", fontSize: "10px" },
    actionText: { minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
    empty: { border: "1px dashed #2c3235", borderRadius: "4px", padding: "8px", color: "#8e99a4" },
    error: { color: "#e02f44", border: "1px solid #e02f44", borderRadius: "4px", padding: "7px", marginBottom: "8px" },
    notice: { color: "#f2cc0c", fontSize: "11px", marginBottom: "7px" },
    success: { color: "#73bf69", fontSize: "11px", marginBottom: "7px" },
  };

  return {
    setters: [
      function (data) {
        PanelPlugin = data.PanelPlugin;
      },
      function (react) {
        React = react;
      },
    ],
    execute: function () {
      exports("plugin", new PanelPlugin(ChostHunterPanel).setPanelOptions(function (builder) {
        return builder.addTextInput({
          path: "apiBase",
          name: "Control API 주소",
          description: "Chost Hunter AI agent 제어 API 주소",
          defaultValue: DEFAULT_API_BASE,
        });
      }));
    },
  };
});
