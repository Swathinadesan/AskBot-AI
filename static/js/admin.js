/*
  Admin dashboard behaviour. Everything rendered here comes from real
  MongoDB-backed endpoints (/admin/api/*, /admin/users) - nothing is
  fabricated client-side. Empty states are shown honestly when a
  collection has no data yet instead of faking a chart.
*/
(function () {
  "use strict";

  var state = {
    overviewData: null,
    activityData: null,
    activityView: "daily",
    charts: {},
  };

  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function fetchJSON(url) {
    return fetch(url).then(function (res) {
      if (res.status === 401) {
        window.location.href = "/admin";
        throw new Error("unauthorized");
      }
      if (!res.ok) throw new Error("Request failed: " + url);
      return res.json();
    });
  }

  function fmtNumber(n) {
    return n === null || n === undefined ? "—" : Number(n).toLocaleString();
  }

  function fmtSeconds(n) {
    if (n === null || n === undefined) return "—";
    if (n < 1) return Math.round(n * 1000) + " ms";
    return n.toFixed(2) + " s";
  }

  function fmtDate(iso) {
    if (!iso) return "—";
    var d = new Date(iso);
    if (isNaN(d.getTime())) return "—";
    return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  }

  function escapeHtml(str) {
    var div = document.createElement("div");
    div.textContent = str === null || str === undefined ? "" : String(str);
    return div.innerHTML;
  }

  function clearEmptyNotes(wrap) {
    wrap.querySelectorAll(".empty-note").forEach(function (n) { n.remove(); });
  }

  function showEmptyNote(wrap, message) {
    var note = document.createElement("div");
    note.className = "empty-note";
    note.textContent = message;
    wrap.appendChild(note);
  }

  // ---------------------------------------------------------------
  // Tabs
  // ---------------------------------------------------------------
  function initTabs() {
    var tabs = document.querySelectorAll("[data-tab]");
    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        tabs.forEach(function (t) { t.classList.remove("is-active"); });
        document.querySelectorAll("[data-panel]").forEach(function (p) { p.classList.remove("is-active"); });
        tab.classList.add("is-active");
        var panel = document.querySelector('[data-panel="' + tab.getAttribute("data-tab") + '"]');
        if (panel) panel.classList.add("is-active");
      });
    });
  }

  // ---------------------------------------------------------------
  // Overview stat cards
  // ---------------------------------------------------------------
  function renderOverview(data) {
    document.getElementById("stat-total-users").textContent = fmtNumber(data.total_users);
    document.getElementById("stat-total-chats").textContent = fmtNumber(data.total_chats);
    document.getElementById("stat-avg-response").textContent = fmtSeconds(data.avg_response_time);
    document.getElementById("stat-kb-size").textContent = fmtNumber(data.total_kb_entries);

    var chatsSub = fmtNumber(data.mongodb_count) + " KB · " + fmtNumber(data.ollama_count) + " AI";
    if (data.unclassified_count) chatsSub += " · " + fmtNumber(data.unclassified_count) + " legacy";
    document.getElementById("stat-chats-sub").textContent = chatsSub;

    document.getElementById("stat-avg-sub").textContent = data.avg_response_time_sample_size
      ? "from " + fmtNumber(data.avg_response_time_sample_size) + " timed replies"
      : "no timed replies yet";

    document.getElementById("stat-kb-sub").textContent =
      fmtNumber(data.curated_kb_entries) + " curated + " + fmtNumber(data.learned_kb_entries) + " auto-learned";

    renderSourceChart(data);
  }

  function renderSourceChart(data) {
    var canvas = document.getElementById("chart-source");
    var wrap = canvas.closest(".chart-canvas-wrap");
    clearEmptyNotes(wrap);

    var total = data.mongodb_count + data.ollama_count + data.unclassified_count;
    if (total === 0) {
      canvas.style.display = "none";
      document.getElementById("source-legend").innerHTML = "";
      showEmptyNote(wrap, "No chats yet — this fills in once students start asking questions.");
      return;
    }
    canvas.style.display = "";

    var colors = { mongodb: cssVar("--teal"), ollama: cssVar("--violet"), legacy: cssVar("--text-faint") };
    var labels = ["Knowledge Base", "Ollama AI"];
    var values = [data.mongodb_count, data.ollama_count];
    var bg = [colors.mongodb, colors.ollama];
    if (data.unclassified_count > 0) {
      labels.push("Legacy / unclassified");
      values.push(data.unclassified_count);
      bg.push(colors.legacy);
    }

    if (state.charts.source) state.charts.source.destroy();
    state.charts.source = new Chart(canvas, {
      type: "doughnut",
      data: { labels: labels, datasets: [{ data: values, backgroundColor: bg, borderWidth: 0, hoverOffset: 6 }] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "68%",
        plugins: { legend: { display: false } },
      },
    });

    var legend = document.getElementById("source-legend");
    legend.innerHTML = labels
      .map(function (label, i) {
        return '<span class="legend-item"><span class="legend-dot" style="background:' + bg[i] + '"></span>' + escapeHtml(label) + "</span>";
      })
      .join("");
  }

  // ---------------------------------------------------------------
  // Activity chart (daily / weekly)
  // ---------------------------------------------------------------
  function bucketWeekly(days) {
    var weeks = [];
    for (var i = 0; i < days.length; i += 7) {
      var slice = days.slice(i, i + 7);
      if (!slice.length) continue;
      var mongodb = 0, ollama = 0, other = 0;
      slice.forEach(function (d) { mongodb += d.mongodb; ollama += d.ollama; other += d.other; });
      var start = new Date(slice[0].date + "T00:00:00Z");
      var end = new Date(slice[slice.length - 1].date + "T00:00:00Z");
      weeks.push({
        label: start.toLocaleDateString(undefined, { month: "short", day: "numeric" }) + "–" + end.toLocaleDateString(undefined, { day: "numeric" }),
        mongodb: mongodb,
        ollama: ollama,
        other: other,
      });
    }
    return weeks;
  }

  function renderActivityChart() {
    var data = state.activityData;
    var canvas = document.getElementById("chart-activity");
    var wrap = canvas.closest(".chart-canvas-wrap");
    clearEmptyNotes(wrap);

    if (!data || !data.has_timestamped_data) {
      canvas.style.display = "none";
      showEmptyNote(wrap, "No dated activity yet. New chats will appear here automatically.");
      return;
    }
    canvas.style.display = "";

    var rows, labels;
    if (state.activityView === "weekly") {
      rows = bucketWeekly(data.activity);
      labels = rows.map(function (r) { return r.label; });
    } else {
      rows = data.activity;
      labels = rows.map(function (r) {
        var d = new Date(r.date + "T00:00:00Z");
        return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
      });
    }

    var mongodbColor = cssVar("--teal");
    var ollamaColor = cssVar("--violet");
    var faint = cssVar("--text-faint");
    var border = cssVar("--border");

    if (state.charts.activity) state.charts.activity.destroy();
    state.charts.activity = new Chart(canvas, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [
          { label: "Knowledge Base", data: rows.map(function (r) { return r.mongodb; }), backgroundColor: mongodbColor, borderRadius: 4, maxBarThickness: 26 },
          { label: "Ollama AI", data: rows.map(function (r) { return r.ollama; }), backgroundColor: ollamaColor, borderRadius: 4, maxBarThickness: 26 },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        scales: {
          x: { stacked: true, grid: { display: false }, ticks: { color: faint, font: { size: 11 } } },
          y: { stacked: true, beginAtZero: true, ticks: { precision: 0, color: faint, font: { size: 11 } }, grid: { color: border } },
        },
        plugins: { legend: { display: false } },
      },
    });
  }

  function initActivityToggle() {
    document.querySelectorAll("[data-activity-view]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        document.querySelectorAll("[data-activity-view]").forEach(function (b) { b.classList.remove("is-active"); });
        btn.classList.add("is-active");
        state.activityView = btn.getAttribute("data-activity-view");
        renderActivityChart();
      });
    });
  }

  // ---------------------------------------------------------------
  // Top questions
  // ---------------------------------------------------------------
  function renderTopQuestions(list) {
    var container = document.getElementById("top-questions-list");
    if (!list.length) {
      container.innerHTML = '<div class="table-empty">No questions asked yet.</div>';
      return;
    }
    var max = list[0].count || 1;
    container.innerHTML = list
      .map(function (item, i) {
        var pct = Math.max(6, Math.round((item.count / max) * 100));
        return (
          '<div class="rank-item">' +
          '<span class="rank-num">' + (i + 1) + "</span>" +
          '<div class="rank-body">' +
          '<div class="rank-text" title="' + escapeHtml(item.question) + '">' + escapeHtml(item.question) + "</div>" +
          '<div class="rank-bar-track"><div class="rank-bar-fill" style="width:' + pct + '%"></div></div>' +
          "</div>" +
          '<span class="rank-count">' + item.count + "×</span>" +
          "</div>"
        );
      })
      .join("");
  }

  // ---------------------------------------------------------------
  // Recent chats table
  // ---------------------------------------------------------------
  function sourceBadge(source) {
    if (source === "mongodb") return '<span class="badge badge-teal"><span class="badge-dot"></span>Knowledge Base</span>';
    if (source === "ollama") return '<span class="badge badge-violet"><span class="badge-dot"></span>Ollama AI</span>';
    return '<span class="badge badge-muted"><span class="badge-dot"></span>Legacy</span>';
  }

  function renderRecentChats(list) {
    var wrap = document.getElementById("chats-table-wrap");
    if (!list.length) {
      wrap.innerHTML = '<div class="table-empty">No chat history yet.</div>';
      return;
    }
    var rows = list
      .map(function (c) {
        return (
          "<tr>" +
          '<td class="cell-primary truncate" title="' + escapeHtml(c.question) + '">' + escapeHtml(c.question) + "</td>" +
          '<td class="truncate" title="' + escapeHtml(c.answer) + '">' + escapeHtml(c.answer) + "</td>" +
          "<td>" + sourceBadge(c.source) + "</td>" +
          '<td class="mono">' + escapeHtml(c.user || "—") + "</td>" +
          '<td class="mono">' + fmtSeconds(c.response_time) + "</td>" +
          '<td class="mono">' + fmtDate(c.timestamp) + "</td>" +
          "</tr>"
        );
      })
      .join("");

    wrap.innerHTML =
      '<div class="table-scroll"><table class="data-table"><thead><tr>' +
      "<th>Question</th><th>Answer</th><th>Source</th><th>Asked by</th><th>Response time</th><th>When</th>" +
      "</tr></thead><tbody>" + rows + "</tbody></table></div>";
  }

  // ---------------------------------------------------------------
  // Users table
  // ---------------------------------------------------------------
  function renderUsers(list) {
    var wrap = document.getElementById("users-table-wrap");
    if (!list.length) {
      wrap.innerHTML = '<div class="table-empty">No registered users yet.</div>';
      return;
    }
    var rows = list
      .map(function (u) {
        return (
          "<tr>" +
          '<td class="cell-primary">' + escapeHtml(u.username || "—") + "</td>" +
          "<td>" + escapeHtml(u.email || "—") + "</td>" +
          '<td class="mono">' + (u.created_at ? fmtDate(u.created_at) : "—") + "</td>" +
          "</tr>"
        );
      })
      .join("");

    wrap.innerHTML =
      '<div class="table-scroll"><table class="data-table"><thead><tr>' +
      "<th>Name</th><th>Email</th><th>Joined</th>" +
      "</tr></thead><tbody>" + rows + "</tbody></table></div>";
  }

  // ---------------------------------------------------------------
  // Boot
  // ---------------------------------------------------------------
  function loadAll() {
    Promise.all([
      fetchJSON("/admin/api/overview"),
      fetchJSON("/admin/api/activity?days=28"),
      fetchJSON("/admin/api/top-questions?limit=8"),
      fetchJSON("/admin/api/recent-chats?limit=30"),
      fetchJSON("/admin/users"),
    ])
      .then(function (results) {
        state.overviewData = results[0];
        state.activityData = results[1];
        renderOverview(results[0]);
        renderActivityChart();
        renderTopQuestions(results[2]);
        renderRecentChats(results[3]);
        renderUsers(results[4]);
      })
      .catch(function (err) {
        if (err && err.message === "unauthorized") return;
        console.error("Dashboard load failed:", err);
      });
  }

  function initThemeSync() {
    var toggle = document.querySelector("[data-theme-toggle]");
    if (!toggle) return;
    toggle.addEventListener("click", function () {
      setTimeout(function () {
        if (state.overviewData) renderSourceChart(state.overviewData);
        if (state.activityData) renderActivityChart();
      }, 60);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initTabs();
    initActivityToggle();
    initThemeSync();
    loadAll();
  });
})();
