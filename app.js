const $ = (s) => document.querySelector(s);
const fmt = (n) => n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fmt0 = (n) => n.toLocaleString("en-US", { maximumFractionDigits: 0 });
const pct = (p) => `${Math.round(p * 100)}%`;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const day = (iso) => {
  const [y, m, d] = iso.split("-").map(Number);
  return `${MONTHS[m - 1]} ${d}, ${y}`;
};
const shortDay = (iso) => {
  const [, m, d] = iso.split("-").map(Number);
  return `${MONTHS[m - 1]} ${d}`;
};

const state = { snaps: [], current: null, filter: "all", local: false };

function pillFor(r) {
  if (r.status === "overdue") return `<span class="pill overdue">${r.action}</span>`;
  if (r.p_late >= 0.5) return `<span class="pill now">${r.action}</span>`;
  if (r.p_late >= 0.3) return `<span class="pill due">${r.action}</span>`;
  return `<span class="pill ok">${r.action}</span>`;
}

function barColor(p) {
  if (p >= 0.5) return "#b45309";
  if (p >= 0.3) return "#ca8a04";
  return "#0f766e";
}

function outcome(r) {
  if (!r.actual_paid) return `<span class="small">Not paid yet</span>`;
  const late = r.actual_paid > r.due;
  const inBand = r.actual_paid >= r.pay_lo && r.actual_paid <= r.pay_hi;
  return `${day(r.actual_paid)}<br><span class="${late ? "miss" : "hit"}">${late ? "Paid late" : "Paid on time"}</span><span class="small">${inBand ? ", inside the range" : ", outside the range"}</span>`;
}

function renderTable(s) {
  let rows = s.invoices;
  if (state.filter === "act") rows = rows.filter((r) => r.action !== "No action needed");
  if (state.filter === "overdue") rows = rows.filter((r) => r.status === "overdue");
  $("#table tbody").innerHTML = rows
    .map(
      (r) => `<tr>
      <td><div class="inv-id">#${r.invoice_id}</div><div class="small">Client ${r.client}</div><div class="small">${r.history}</div></td>
      <td class="num">${fmt(r.amount)}</td>
      <td>${day(r.due)}<div class="small">${r.status === "overdue" ? `${r.age_days - daysBetween(r.issued, r.due)} days overdue` : `sent ${r.age_days} days ago`}</div></td>
      <td>${
        r.status === "overdue"
          ? `<span class="small">Already past due</span>`
          : `<div class="bar"><div class="track"><div class="fill" style="width:${r.p_late * 100}%;background:${barColor(r.p_late)}"></div></div><span class="pct">${pct(r.p_late)}</span></div>`
      }</td>
      <td>${day(r.pay_mid)}<div class="small">80% range: ${shortDay(r.pay_lo)} to ${shortDay(r.pay_hi)}</div></td>
      <td>${pillFor(r)}</td>
      <td class="reveal-col">${outcome(r)}</td>
    </tr>`
    )
    .join("");
  $("#table-foot").textContent = `${rows.length} of ${s.invoices.length} unpaid invoices shown. TabPFN learned from the ${s.train_rows} most recent invoices paid before ${day(s.as_of)}.`;
}

function daysBetween(a, b) {
  return Math.round((new Date(b) - new Date(a)) / 86400000);
}

function renderKpis(s) {
  const next4 = s.weeks.slice(0, 4).reduce((t, w) => t + w.expected, 0);
  const act = s.invoices.filter((r) => r.action !== "No action needed" && r.action !== "Remind on the due date").length;
  const overdue = s.invoices.filter((r) => r.status === "overdue").length;
  const actual4 = s.weeks[0].actual == null ? null : s.weeks.slice(0, 4).reduce((t, w) => t + w.actual, 0);
  $("#kpis").innerHTML = `
    <div class="kpi"><div class="label">Unpaid invoices on ${day(s.as_of)}</div><div class="value">${s.open_count}</div><div class="sub">${fmt0(s.open_amount)} outstanding</div></div>
    <div class="kpi"><div class="label">Expected in the next 4 weeks</div><div class="value">${fmt0(next4)}</div><div class="sub">From invoices already sent. Weekly ranges in the chart${
      actual4 != null ? `<span class="reveal-inline">. Actually paid: ${fmt0(actual4)}</span>` : ""
    }</div></div>
    <div class="kpi"><div class="label">Chase today</div><div class="value">${act}</div><div class="sub">${overdue} overdue, ${act - overdue} likely to be late</div></div>
    <div class="kpi"><div class="label">Model run time</div><div class="value">${s.seconds != null ? `${s.seconds} s` : "n/a"}</div><div class="sub">TabPFN v2 on a laptop CPU</div></div>`;
}

function renderCash(s) {
  const W = 520, H = 240, L = 46, B = 34, T = 12, R = 10;
  const max = Math.max(...s.weeks.map((w) => Math.max(w.hi, w.actual ?? 0))) * 1.1 || 1;
  const bw = (W - L - R) / s.weeks.length;
  const y = (v) => H - B - (v / max) * (H - B - T);
  const ticks = [0, max / 2, max].map((v) => `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="#e3e7e4"/><text x="${L - 6}" y="${y(v) + 4}" font-size="11" text-anchor="end" fill="#5d6b66">${fmt0(v)}</text>`).join("");
  const bars = s.weeks
    .map((w, i) => {
      const x = L + i * bw + bw * 0.18, wd = bw * 0.64, cx = x + wd / 2;
      const dot = w.actual != null ? `<circle class="reveal-svg" cx="${cx}" cy="${y(w.actual)}" r="5" fill="#17201d"/>` : "";
      return `<rect x="${x}" y="${y(w.expected)}" width="${wd}" height="${H - B - y(w.expected)}" rx="3" fill="#99d0c8"/>
        <line x1="${cx}" x2="${cx}" y1="${y(w.lo)}" y2="${y(w.hi)}" stroke="#0f766e" stroke-width="2"/>
        <line x1="${cx - 6}" x2="${cx + 6}" y1="${y(w.hi)}" y2="${y(w.hi)}" stroke="#0f766e" stroke-width="2"/>
        <line x1="${cx - 6}" x2="${cx + 6}" y1="${y(w.lo)}" y2="${y(w.lo)}" stroke="#0f766e" stroke-width="2"/>
        ${dot}
        <text x="${cx}" y="${H - B + 16}" font-size="11" text-anchor="middle" fill="#5d6b66">${shortDay(w.start)}</text>`;
    })
    .join("");
  $("#cash").innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Weekly cash forecast">${ticks}${bars}
    <text x="${L}" y="${H - 2}" font-size="11" fill="#5d6b66">Week starting</text></svg>`;
  document.querySelectorAll(".reveal-svg").forEach((el) => (el.style.display = document.body.classList.contains("revealed") ? "" : "none"));
}

function show(s) {
  state.current = s;
  renderKpis(s);
  renderTable(s);
  renderCash(s);
}

function renderDates() {
  $("#dates").innerHTML = state.snaps
    .map((s, i) => `<button role="tab" data-i="${i}">${shortDay(s.as_of)}, ${s.as_of.slice(0, 4)}</button>`)
    .join("");
  $("#dates").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    select(Number(b.dataset.i));
  });
}

function select(i) {
  document.querySelectorAll("#dates button").forEach((b) => b.classList.toggle("active", Number(b.dataset.i) === i));
  show(state.snaps[i]);
}

function renderEvidence(bt, check) {
  const d = bt.dataset;
  $("#ev-lead").innerHTML = `IBM's public sample has ${fmt0(d.invoices)} invoices from ${d.clients} business clients, ${pct(d.late_share)} of them paid late. For each month from January to October 2013, every model below was trained only on invoices already paid before that month started, then asked about the invoices sent during the month: ${fmt0(bt.summary[0].invoices)} predictions in total. "Chase recall" is the share of late invoices you would catch by chasing only the riskiest 20% each month.`;
  const best = (k, lower) => {
    const vals = bt.summary.map((r) => r[k]).filter((v) => v != null);
    return lower ? Math.min(...vals) : Math.max(...vals);
  };
  const cols = [
    ["auc", "Ranking (AUC)", false],
    ["brier", "Brier score", true],
    ["chase_recall", "Chase recall", false],
    ["days_mae", "Pay day error (days)", true],
    ["coverage_80", "80% range hit rate", null],
  ];
  const head = `<thead><tr><th>Model</th>${cols.map((c) => `<th class="num">${c[1]}</th>`).join("")}</tr></thead>`;
  const body = bt.summary
    .map((r) => `<tr class="${r.model === "TabPFN" ? "best" : ""}"><td>${r.model}</td>${cols
      .map(([k, , lower]) => {
        const v = r[k];
        if (v == null) return `<td class="num small">n/a</td>`;
        const isBest = lower !== null && v === best(k, lower);
        const txt = k === "chase_recall" || k === "coverage_80" ? pct(v) : v;
        return `<td class="num">${isBest ? `<strong>${txt}</strong>` : txt}</td>`;
      })
      .join("")}</tr>`)
    .join("");
  $("#ev-table").innerHTML = head + `<tbody>${body}</tbody>`;
  const by = Object.fromEntries(bt.summary.map((r) => [r.model, r]));
  const t = by["TabPFN"], lin = by["Logistic / linear"];
  $("#ev-honest").innerHTML = `The honest reading: on this data a plain logistic and linear regression is as accurate as TabPFN (AUC ${lin.auc} against ${t.auc}, pay day error ${lin.days_mae} against ${t.days_mae} days). Both clearly beat the base rate, and TabPFN beats gradient-boosted trees, whose 80% ranges caught the real date only ${pct(by["Gradient-boosted trees"].coverage_80)} of the time. What TabPFN adds is a separate distribution for every invoice, which the table below tests and which Cashcast uses to update an estimate as an invoice ages.`;
  if (bt.adaptivity) {
    const a = bt.adaptivity;
    const groups = ["Steady clients", "Middle", "Erratic clients"];
    const models = ["TabPFN", "Logistic / linear", "Gradient-boosted trees"];
    const cell = (m, g) => a.rows.find((r) => r.model === m && r.group === g);
    $("#adapt-table").innerHTML = `<thead><tr><th>Model</th>${groups.map((g) => `<th class="num">${g}</th>`).join("")}</tr></thead><tbody>${models
      .map((m) => `<tr class="${m === "TabPFN" ? "best" : ""}"><td>${m}</td>${groups.map((g) => { const c = cell(m, g); return `<td class="num">${pct(c.coverage_80)} hit, ${c.band_width} days wide</td>`; }).join("")}</tr>`)
      .join("")}</tbody>`;
    $("#adapt-table").insertAdjacentHTML("afterend", `<p class="foot">Clients are split into thirds by how much their past payment times varied (standard deviation under ${a.spread_cuts_days[0]} days, ${a.spread_cuts_days[0]} to ${a.spread_cuts_days[1]}, over ${a.spread_cuts_days[1]}). A good range is narrow for steady clients and wide for erratic ones while still catching about 80%. The linear model uses one width for everyone.</p>`);
  }
  const c = bt.calibration;
  const W = 300, H = 200, L = 34, B = 30, T = 8, R = 16;
  const x = (v) => L + v * (W - L - R), y = (v) => H - B - v * (H - B - T);
  const pts = c.map((b) => `<circle cx="${x(b.predicted)}" cy="${y(b.actual)}" r="${Math.max(4, Math.sqrt(b.n) / 2)}" fill="#0f766e" fill-opacity="0.75"><title>${b.bin}: ${b.n} invoices, predicted ${pct(b.predicted)}, actual ${pct(b.actual)}</title></circle>`).join("");
  $("#calib").innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Calibration chart">
    <line x1="${x(0)}" y1="${y(0)}" x2="${x(1)}" y2="${y(1)}" stroke="#cbd5d1" stroke-dasharray="4 4"/>
    <line x1="${L}" y1="${H - B}" x2="${W - R}" y2="${H - B}" stroke="#94a3a0"/><line x1="${L}" y1="${T}" x2="${L}" y2="${H - B}" stroke="#94a3a0"/>
    ${[0, 0.5, 1].map((v) => `<text x="${x(v)}" y="${H - B + 14}" font-size="10" text-anchor="middle" fill="#5d6b66">${pct(v)}</text><text x="${L - 4}" y="${y(v) + 3}" font-size="10" text-anchor="end" fill="#5d6b66">${pct(v)}</text>`).join("")}
    <text x="${(L + W) / 2}" y="${H - 2}" font-size="10" text-anchor="middle" fill="#5d6b66">Predicted chance of paying late (TabPFN)</text>
    ${pts}</svg><p class="foot">Each dot groups invoices by predicted chance; its height is the share that was really paid late. Dots near the dashed line mean the percentages can be taken at face value.</p>`;
  $("#replay-facts").innerHTML = [
    `${check.snapshots} replay dates, ${fmt0(check.open_invoice_rows)} unpaid-invoice rows scored.`,
    `Not-yet-due invoices: ranking AUC ${check.late_auc}, Brier ${check.late_brier} (late share ${pct(check.late_base_rate)}).`,
    check.reminder_now_rows ? `Of ${check.reminder_now_rows} "send a reminder now" flags, ${pct(check.reminder_now_late_share)} were in fact paid late.` : null,
    `The actual payment date fell inside the 80% range ${pct(check.pay_band_coverage)} of the time; typical miss ${check.pay_date_mae_days} days.`,
    `Weekly cash: actual inside the 80% range in ${pct(check.cash_band_coverage)} of ${check.cash_weeks} weeks.`,
    `About ${check.seconds_per_snapshot} s per date on a laptop CPU.`,
  ]
    .filter(Boolean)
    .map((t) => `<li>${t}</li>`)
    .join("");
}

function wireCommon() {
  $("#reveal").addEventListener("change", (e) => {
    document.body.classList.toggle("revealed", e.target.checked);
    if (state.current) renderCash(state.current);
  });
  document.querySelectorAll(".chip").forEach((c) =>
    c.addEventListener("click", () => {
      document.querySelectorAll(".chip").forEach((x) => x.classList.toggle("active", x === c));
      state.filter = c.dataset.filter;
      if (state.current) renderTable(state.current);
    })
  );
}

async function detectLocal() {
  if (!["localhost", "127.0.0.1"].includes(location.hostname)) return false;
  try {
    const r = await fetch("api/health", { cache: "no-store" });
    if (!r.ok) return false;
    const j = await r.json();
    return j.local === true;
  } catch {
    return false;
  }
}

function wireLocal() {
  $("#own-local").hidden = false;
  $("#own-static").hidden = true;
  $("#asof").value = new Date().toISOString().slice(0, 10);
  $("#upload").addEventListener("submit", async (e) => {
    e.preventDefault();
    const file = $("#file").files[0];
    if (file) await scoreLocal(await file.text(), $("#asof").value, file.name, e.submitter);
  });
  $("#try-sample").addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    const text = await fetch("sample.csv").then((r) => r.text());
    await scoreLocal(text, "2013-09-01", "sample.csv", btn);
  });
}

async function scoreLocal(text, asOf, name, btn) {
  btn.disabled = true;
  $("#upload-status").textContent = "TabPFN is reading the history. This takes about 10 to 60 seconds on a CPU.";
  try {
    const r = await fetch(`api/score?as_of=${asOf}`, { method: "POST", body: text, headers: { "Content-Type": "text/csv" } });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || "Scoring failed");
    $("#mode-banner").classList.add("local");
    $("#mode-title").textContent = "Local mode.";
    $("#mode-text").textContent = `Scored ${j.open_count} unpaid invoices from ${name} as of ${day(j.as_of)}. The file was processed on this computer only.`;
    $("#dates").hidden = true;
    $(".reveal").hidden = true;
    document.body.classList.remove("revealed");
    show(j);
    $("#upload-status").textContent = `Done in ${j.seconds} s.`;
    window.scrollTo({ top: 0, behavior: "smooth" });
  } catch (err) {
    $("#upload-status").textContent = err.message;
  } finally {
    btn.disabled = false;
  }
}

async function main() {
  wireCommon();
  const [replay, bt] = await Promise.all([
    fetch("data/replay.json").then((r) => r.json()),
    fetch("data/backtest.json").then((r) => r.json()),
  ]);
  state.snaps = replay.snapshots;
  renderDates();
  select(Math.min(7, state.snaps.length - 1));
  renderEvidence(bt, replay.check);
  if (await detectLocal()) wireLocal();
}

main();
