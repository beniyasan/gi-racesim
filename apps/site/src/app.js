import { ContractError, MAX_BYTES, validateBundle } from "./validator.js";
import { sha256Hex, utf8Bytes } from "./content-hash.js";

const root = document.querySelector("#app");
const fileInput = document.querySelector("#bundle-file");
const fixtureButton = document.querySelector("#load-fixture");
let schemaPromise;

function schema() {
  schemaPromise ??= fetch("./public/schema.json", { cache: "no-store" }).then(async (response) => {
    if (!response.ok) throw new Error(`schema HTTP ${response.status}`);
    return response.json();
  });
  return schemaPromise;
}

function escapeText(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[character]));
}

function originLabel(origin) {
  return { synthetic: "合成データ", baseline_prediction: "基準予測", learned_prediction: "学習モデル予測" }[origin] ?? origin;
}

function render(bundle, contentHash) {
  const corners = bundle.simulation.representative_trials[0]?.corners ?? [];
  const cornerHtml = corners.map((corner) => {
    const groups = corner.groups.map((group) => `<li>${escapeText(group.members.join("・"))}${group.gap_from_previous ? ` <small>${escapeText(group.gap_from_previous)}</small>` : ""}</li>`).join("");
    return `<section class="corner"><h3>${escapeText(corner.checkpoint)}</h3><ol>${groups}</ol>${corner.unobserved_gate_numbers.length ? `<p class="warning">不明: ${escapeText(corner.unobserved_gate_numbers.join("・"))}</p>` : ""}</section>`;
  }).join("");
  root.innerHTML = `<article class="result"><div class="result-heading"><div><p class="eyebrow">${escapeText(originLabel(bundle.origin))}</p><h2>${escapeText(bundle.race.name)}</h2><p>${escapeText(bundle.race.course)} / ${escapeText(bundle.race.surface)} / ${escapeText(bundle.race.distance_m)}m</p></div><span class="badge">${escapeText(bundle.schema_version)}</span></div><dl class="meta"><div><dt>レースID</dt><dd>${escapeText(bundle.race_id)}</dd></div><div><dt>入力時点</dt><dd>${escapeText(bundle.as_of)}</dd></div><div><dt>データ版</dt><dd>${escapeText(bundle.dataset_id)}</dd></div><div><dt>入力SHA-256</dt><dd><code>${escapeText(contentHash)}</code></dd></div></dl><section><h3>ラップ分布</h3><div class="laps">${bundle.simulation.lap_quantiles.map((q) => `<span><b>${escapeText(q.segment_end_m)}m</b><br>${escapeText(q.p10_s ?? "不明")} / ${escapeText(q.p50_s ?? "不明")} / ${escapeText(q.p90_s ?? "不明")}</span>`).join("")}</div></section><section><h3>品質</h3>${bundle.quality.notes.map((note) => `<p>${escapeText(note)}</p>`).join("")}<p class="${bundle.quality.missing_fields.length ? "warning" : "ok"}">${bundle.quality.missing_fields.length ? `観測不足: ${escapeText(bundle.quality.missing_fields.join(", "))}` : "観測不足の記録なし"}</p></section><section><h3>代表試行の地点別隊列</h3><div class="corners">${cornerHtml}</div></section></article>`;
}

function showError(error) {
  root.innerHTML = `<p class="error">読み込みできません: ${escapeText(error.message)}</p>`;
}

async function loadJsonText(text) {
  if (new TextEncoder().encode(text).byteLength > MAX_BYTES) throw new ContractError("bundle exceeds 5 MiB");
  const value = JSON.parse(text);
  validateBundle(value, await schema());
  render(value, await sha256Hex(utf8Bytes(text)));
}

fileInput.addEventListener("change", async () => {
  const file = fileInput.files?.[0];
  if (!file) return;
  try {
    if (file.size > MAX_BYTES) throw new ContractError("bundle exceeds 5 MiB");
    await loadJsonText(await file.text());
  } catch (error) {
    showError(error);
  }
});

fixtureButton.addEventListener("click", async () => {
  try {
    const response = await fetch("./public/fixtures/synthetic-race.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`fixture HTTP ${response.status}`);
    await loadJsonText(await response.text());
  } catch (error) {
    showError(error);
  }
});

root.innerHTML = "<p>合成fixtureを読み込むか、Macから書き出したJSONを選択してください。</p>";
