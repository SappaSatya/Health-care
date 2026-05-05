const metricGrid = document.getElementById("metricGrid");
const sourceLabel = document.getElementById("sourceLabel");
const generatedLabel = document.getElementById("generatedLabel");
const topDiseases = document.getElementById("topDiseases");
const topPatients = document.getElementById("topPatients");
const observationAlerts = document.getElementById("observationAlerts");
const complexPatientsBody = document.getElementById("complexPatientsBody");
const visitsTrend = document.getElementById("visitsTrend");
const genderBreakdown = document.getElementById("genderBreakdown");
const insightButton = document.getElementById("insightButton");
const insightQuestion = document.getElementById("insightQuestion");
const insightOutput = document.getElementById("insightOutput");

function formatNumber(value) {
  return new Intl.NumberFormat().format(value);
}

function formatDateTime(value) {
  if (!value) {
    return "Unknown time";
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function buildMetricCards(summary) {
  const metrics = [
    ["Patients", summary.total_patients],
    ["Visits", summary.total_visits],
    ["Avg. Visits / Patient", summary.average_visits_per_patient],
    ["Diagnoses", summary.total_diagnoses],
    ["Medications", summary.total_medications],
    ["Observations", summary.total_observations],
    ["Abnormal Observations", summary.abnormal_observations],
    ["Multi-Diagnosis Patients", summary.patients_with_multiple_diagnoses],
  ];

  metricGrid.innerHTML = metrics
    .map(
      ([label, value]) => `
        <article class="metric">
          <span class="metric-label">${label}</span>
          <strong class="metric-value">${formatNumber(value)}</strong>
        </article>
      `
    )
    .join("");
}

function renderBarList(target, rows, labelKey, valueKey, colorClass = "") {
  const maxValue = Math.max(...rows.map((row) => row[valueKey]), 1);
  target.innerHTML = rows
    .map((row) => {
      const width = (row[valueKey] / maxValue) * 100;
      return `
        <div class="bar-row">
          <div class="bar-head">
            <span>${row[labelKey]}</span>
            <strong>${formatNumber(row[valueKey])}</strong>
          </div>
          <div class="bar-track">
            <div class="bar-fill ${colorClass}" style="width: ${width}%"></div>
          </div>
        </div>
      `;
    })
    .join("");
}

function renderComplexPatients(rows) {
  complexPatientsBody.innerHTML = rows
    .map(
      (row) => `
        <tr>
          <td>
            <strong>${row.name}</strong><br />
            <span class="disease-list">${row.patient_id}</span>
          </td>
          <td>${formatNumber(row.visits)}</td>
          <td>${formatNumber(row.disease_count)}</td>
          <td class="disease-list">${row.diseases.join(", ")}</td>
        </tr>
      `
    )
    .join("");
}

function renderGenderBreakdown(rows) {
  const total = rows.reduce((sum, row) => sum + row.count, 0) || 1;
  const colors = ["#67d6c3", "#ff8f6b", "#f5c45d", "#88a7ff"];

  const track = rows
    .map((row, index) => {
      const width = (row.count / total) * 100;
      return `<div class="stack-segment" style="width:${width}%; background:${colors[index % colors.length]}"></div>`;
    })
    .join("");

  const legend = rows
    .map(
      (row, index) => `
        <div class="legend-item">
          <span><span class="legend-swatch" style="background:${colors[index % colors.length]}"></span>${row.label}</span>
          <strong>${formatNumber(row.count)}</strong>
        </div>
      `
    )
    .join("");

  genderBreakdown.innerHTML = `
    <div class="stack-track">${track}</div>
    <div class="stack-legend">${legend}</div>
  `;
}

function renderVisitsTrend(rows) {
  const width = 900;
  const height = 280;
  const padding = { top: 24, right: 24, bottom: 36, left: 42 };
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;
  const maxVisits = Math.max(...rows.map((row) => row.visits), 1);

  const points = rows.map((row, index) => {
    const x = padding.left + (index / Math.max(rows.length - 1, 1)) * innerWidth;
    const y = padding.top + innerHeight - (row.visits / maxVisits) * innerHeight;
    return { ...row, x, y };
  });

  const polyline = points.map((point) => `${point.x},${point.y}`).join(" ");
  const horizontalLines = 4;
  const grid = Array.from({ length: horizontalLines + 1 }, (_, index) => {
    const y = padding.top + (index / horizontalLines) * innerHeight;
    const value = Math.round(maxVisits - (index / horizontalLines) * maxVisits);
    return `
      <line class="chart-grid-line" x1="${padding.left}" y1="${y}" x2="${width - padding.right}" y2="${y}"></line>
      <text class="chart-axis-label" x="8" y="${y + 4}">${value}</text>
    `;
  }).join("");

  const labels = points
    .map(
      (point, index) =>
        index % Math.ceil(rows.length / 6 || 1) === 0
          ? `<text class="chart-axis-label" x="${point.x}" y="${height - 8}" text-anchor="middle">${point.month_label}</text>`
          : ""
    )
    .join("");

  const dots = points
    .map(
      (point) => `
        <circle class="chart-dot" cx="${point.x}" cy="${point.y}" r="4"></circle>
        <text class="chart-axis-label" x="${point.x}" y="${point.y - 10}" text-anchor="middle">${point.visits}</text>
      `
    )
    .join("");

  visitsTrend.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Visits by month chart">
      ${grid}
      <polyline class="chart-line" points="${polyline}"></polyline>
      ${dots}
      ${labels}
    </svg>
  `;
}

async function loadDashboard() {
  const response = await fetch("/api/dashboard");
  const data = await response.json();

  sourceLabel.textContent = `${data.patient_count} patients from healthcare_data.json`;
  generatedLabel.textContent = `Snapshot generated ${formatDateTime(data.generated_at)} from ${data.source}`;

  buildMetricCards(data.summary);
  renderVisitsTrend(data.visits_by_month);
  renderGenderBreakdown(data.gender_breakdown);
  renderBarList(
    topDiseases,
    data.top_diseases.map((row) => ({ ...row, label: row.disease })),
    "label",
    "visit_count"
  );
  renderBarList(topPatients, data.top_patients_by_visits, "name", "visits", "teal");
  renderBarList(
    observationAlerts,
    data.observation_alerts.map((row) => ({ ...row, label: row.observation })),
    "label",
    "count"
  );
  renderComplexPatients(data.patients_with_multiple_diseases);
}

async function requestInsight() {
  insightButton.disabled = true;
  insightButton.textContent = "Thinking...";
  insightOutput.textContent = "Generating insight...";

  try {
    const response = await fetch("/api/ai-insights", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: insightQuestion.value.trim() }),
    });
    const data = await response.json();
    insightOutput.textContent = data.insights || data.message || "No insight returned.";
  } catch (error) {
    insightOutput.textContent = `Could not load AI insights: ${error.message}`;
  } finally {
    insightButton.disabled = false;
    insightButton.textContent = "Generate Insight";
  }
}

insightButton.addEventListener("click", requestInsight);
loadDashboard().catch((error) => {
  metricGrid.innerHTML = `<article class="metric"><span class="metric-label">Error</span><strong class="metric-value">Failed</strong></article>`;
  insightOutput.textContent = `Dashboard failed to load: ${error.message}`;
});
