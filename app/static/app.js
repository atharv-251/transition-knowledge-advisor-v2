const API = "/api/v1/transitions";
const PAGE_SIZE = 10;
const pageState = { "master-plan": 1, schedule: 1 };
let transition = null;

const byId = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[character]);
const value = (row, key) => escapeHtml(row[key] || "-");

async function request(path) {
  const response = await fetch(path);
  if (!response.ok) { const body = await response.json().catch(() => ({})); throw new Error(body.detail || "Unable to read transition documents."); }
  return response.json();
}

function notify(message) { const notice = byId("notice"); notice.textContent = message; notice.className = "notice show"; window.setTimeout(() => { notice.className = "notice"; }, 4000); }
function rows(items, columnCount) { return items.length ? items.join("") : `<tr><td class="empty" colspan="${columnCount}">No records found in this document.</td></tr>`; }

function paginate(items, view, renderRow) {
  const pageCount = Math.max(1, Math.ceil(items.length / PAGE_SIZE));
  pageState[view] = Math.min(pageState[view], pageCount);
  const page = pageState[view]; const start = (page - 1) * PAGE_SIZE;
  return { html: rows(items.slice(start, start + PAGE_SIZE).map(renderRow), view === "schedule" ? 9 : 6), page };
}

function pagination(view, count) {
  const target = byId(`${view}-pagination`); const pageCount = Math.max(1, Math.ceil(count / PAGE_SIZE)); const page = pageState[view];
  const numberButtons = Array.from({ length: pageCount }, (_, index) => `<button class="page-button ${page === index + 1 ? "active" : ""}" type="button" data-page-view="${view}" data-page-number="${index + 1}">${index + 1}</button>`).join("");
  target.innerHTML = `<span>${count ? `${(page - 1) * PAGE_SIZE + 1}-${Math.min(page * PAGE_SIZE, count)} of ${count}` : "0 records"}</span><div class="page-controls"><button class="page-button" type="button" data-page-view="${view}" data-page-number="${page - 1}" ${page === 1 ? "disabled" : ""}>Previous</button>${numberButtons}<button class="page-button" type="button" data-page-view="${view}" data-page-number="${page + 1}" ${page === pageCount ? "disabled" : ""}>Next</button></div>`;
}

function setView(view) {
  document.querySelectorAll(".tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.view === view));
  document.querySelectorAll(".view").forEach((panel) => { const active = panel.dataset.panel === view; panel.hidden = !active; panel.classList.toggle("active", active); });
}

function setWorkspaceView(view) {
  document.querySelectorAll(".workspace-nav-button").forEach((button) => button.classList.toggle("active", button.dataset.workspaceView === view));
  byId("upload-transition-panel").hidden = view !== "upload";
  byId("transition-list-panel").hidden = view !== "select";
  byId("workspace").hidden = view !== "current" || !transition;
  byId("empty-state").hidden = view !== "current" || Boolean(transition);
}

function setProductView(view) {
  document.querySelectorAll(".product-nav-button").forEach((button) => button.classList.toggle("active", button.dataset.productView === view));
  byId("tracker-app").hidden = view !== "tracker";
  byId("scheduler-app").hidden = view !== "scheduler";
}

function recipientList(value) {
  return value.split(",").map((recipient) => recipient.trim()).filter(Boolean);
}

function transitionRecipients() {
  if (!transition) return [];
  const attendeeFields = transition.schedule.flatMap((session) => [session["Required Attendees"], session["Optional Attendees"]]);
  const recipients = attendeeFields.flatMap((field) => String(field || "").replace(/;/g, ",").split(",")).map((recipient) => recipient.trim()).filter(Boolean).map((recipient) => recipient.toLowerCase());
  return [...new Set(recipients)];
}

function renderSchedulerContext() {
  byId("scheduler-transition-name").textContent = transition ? transition.name : "Select a transition in KT Tracker";
  byId("scheduler-schedule-file").textContent = transition ? transition.files.schedule : "No schedule loaded";
  const recipients = transitionRecipients();
  byId("scheduler-recipients").value = recipients.join(", ");
  byId("scheduler-recipient-summary").textContent = transition ? `${recipients.length} participant${recipients.length === 1 ? "" : "s"} loaded from this transition` : "No transition selected";
  byId("scheduler-send-button").disabled = !transition;
}

function renderSchedulerResult(result) {
  const delivered = result.sent + result.dry_run;
  const firstError = result.errors[0] || "";
  const deliveryMessage = firstError.includes("Need to authenticate via SMTP-AUTH") ? "The SMTP relay requires authentication before it can send invites." : firstError ? "The SMTP relay could not send the invite. Check the server settings and try again." : "Each recipient is limited to one invitation for this run.";
  byId("scheduler-results").hidden = false;
  byId("scheduler-results").innerHTML = `<div class="result-metric"><span>Schedule sessions</span><strong>${result.total_items}</strong></div><div class="result-metric"><span>Invites sent</span><strong>${result.sent}</strong></div><div class="result-metric"><span>Skipped</span><strong>${result.skipped}</strong></div><div class="result-detail"><strong>${delivered ? "Invitation run completed" : "Invite delivery needs attention"}</strong><span>${escapeHtml(deliveryMessage)}</span></div>`;
}

function render() {
  const summary = transition.summary;
  byId("transition-name").textContent = transition.name;
  byId("transition-window").textContent = summary["Start & End Dates"] || "Transition documents loaded";
  byId("master-plan-file").textContent = transition.files.master_plan;
  byId("schedule-file").textContent = transition.files.schedule;
  byId("teams-transcript-file").textContent = transition.files.teams_transcript || "Not attached";
  byId("current-transition-label").textContent = transition.name;
  byId("topic-count").textContent = transition.master_plan.length;
  byId("session-count").textContent = transition.schedule.length;
  byId("capacity-value").textContent = summary["Generated Topic Capacity"] || "-";
  byId("approval-value").textContent = summary["Approval Status"] || "-";
  renderSchedulerContext();
  byId("summary-grid").innerHTML = Object.entries(summary).map(([key, entry]) => `<div class="summary-item"><span>${escapeHtml(key)}</span><strong>${escapeHtml(entry)}</strong></div>`).join("");
  byId("availability-body").innerHTML = rows(transition.availability.map((row) => `<tr><td>${value(row, "Date")}</td><td>${value(row, "Day of Week")}</td><td>${value(row, "Calendar Status")}</td><td>${value(row, "Bank Holiday / Leave Reason")}</td><td>${value(row, "Assigned Sessions")}</td></tr>`), 5);
  const masterPlan = paginate(transition.master_plan, "master-plan", (row) => `<tr><td>${value(row, "Level Type")}</td><td>${value(row, "Topic / Subtopic Name")}</td><td>${value(row, "Category")}</td><td>${value(row, "Est. Hours")}</td><td>${value(row, "Delivery Method")}</td><td>${value(row, "Weightage %")}</td></tr>`);
  byId("master-plan-body").innerHTML = masterPlan.html; byId("master-plan-records").textContent = `${transition.master_plan.length} entries`; pagination("master-plan", transition.master_plan.length);
  const schedule = paginate(transition.schedule, "schedule", (row) => `<tr><td>${value(row, "Session Title")}</td><td>${value(row, "Level")}</td><td>${value(row, "Scheduled Date")}</td><td>${value(row, "Start Time")} - ${value(row, "End Time")}</td><td>${value(row, "Duration Hours")} hrs</td><td>${value(row, "Delivery Mode")}</td><td>${value(row, "Assigned SME")}</td><td>${value(row, "Assigned Receiver")}</td><td class="status">${value(row, "Status")}</td></tr>`);
  byId("schedule-body").innerHTML = schedule.html; byId("scheduler-schedule-records").textContent = `${transition.schedule.length} sessions`; pagination("schedule", transition.schedule.length);
  byId("calendar-grid").innerHTML = transition.calendar.map((day) => `<article class="calendar-day"><header><h4>${escapeHtml(day.day)}</h4><span>${escapeHtml(day.date)}</span></header>${day.sessions.map((session) => `<div class="session-card"><span>${escapeHtml(session["Start Time"])} - ${escapeHtml(session["End Time"])} · ${escapeHtml(session["Duration Hours"])}h</span><strong>${escapeHtml(session["Session Title"])}</strong><span>${escapeHtml(session["Delivery Mode"])} · ${escapeHtml(session["Assigned SME"])}</span></div>`).join("")}</article>`).join("");
  byId("validation-body").innerHTML = rows(transition.validation.map((row) => `<tr><td>${value(row, "Governance Check")}</td><td>${value(row, "Category")}</td><td class="pass">${value(row, "Result")}</td><td>${value(row, "Severity")}</td><td>${value(row, "Compliance Message")}</td></tr>`), 5);
}

async function loadTransition(transitionId) { transition = await request(`${API}/${encodeURIComponent(transitionId)}`); pageState["master-plan"] = 1; pageState.schedule = 1; render(); }
async function loadLatestTransition() { transition = await request(`${API}/latest`); pageState["master-plan"] = 1; pageState.schedule = 1; render(); }

async function renderTransitionList() {
  const transitions = await request(API);
  byId("transition-list").innerHTML = transitions.length ? transitions.map((item) => `<button class="transition-list-item" type="button" data-transition-id="${escapeHtml(item.id)}"><strong>${escapeHtml(item.name)}</strong><span>${escapeHtml(item.master_plan_file)} · ${escapeHtml(item.schedule_file)}</span><small>${item.teams_transcript ? `Teams Transcript: ${escapeHtml(item.teams_transcript)}` : "No Teams Transcript attached"}</small></button>`).join("") : `<p class="empty">No uploaded transitions found.</p>`;
}

async function init() {
  try {
    const healthResponse = await fetch("/api/v1/health");
    const health = await healthResponse.json(); const badge = byId("health-status"); badge.textContent = health.status === "healthy" ? "Healthy" : health.status; badge.className = "health healthy";
    await loadLatestTransition(); setWorkspaceView("current");
  } catch (error) { setWorkspaceView("current"); if (!String(error.message).includes("No transition documents")) notify(error.message); }
}

byId("upload-form").addEventListener("submit", async (event) => {
  event.preventDefault(); const button = event.target.querySelector("button"); button.disabled = true; button.textContent = "Uploading...";
  try { const response = await fetch(`${API}/upload`, { method: "POST", body: new FormData(event.target) }); if (!response.ok) { const body = await response.json().catch(() => ({})); throw new Error(body.detail || "Upload failed."); } const result = await response.json(); transition = result.transition; pageState["master-plan"] = 1; pageState.schedule = 1; render(); event.target.reset(); setWorkspaceView("current"); }
  catch (error) { notify(error.message); }
  finally { button.disabled = false; button.textContent = "Upload transition"; }
});
byId("teams-transcript-form").addEventListener("submit", async (event) => {
  event.preventDefault(); if (!transition) return; const button = event.target.querySelector("button"); button.disabled = true; button.textContent = "Uploading...";
  try { const response = await fetch(`${API}/${encodeURIComponent(transition.id)}/teams-transcript`, { method: "POST", body: new FormData(event.target) }); if (!response.ok) { const body = await response.json().catch(() => ({})); throw new Error(body.detail || "Transcript upload failed."); } const result = await response.json(); transition = result.transition; render(); event.target.reset(); notify("Teams Transcript attached to this transition."); }
  catch (error) { notify(error.message); }
  finally { button.disabled = false; button.textContent = "Upload transcript"; }
});
byId("scheduler-form").addEventListener("submit", async (event) => {
  event.preventDefault(); if (!transition) { notify("Select a transition before scheduling an invite."); return; }
  const recipients = transitionRecipients(); if (!recipients.length) { notify("No recipients were found in this transition schedule."); return; }
  const button = byId("scheduler-send-button"); button.disabled = true; button.textContent = "Sending...";
  try { const response = await fetch(`${API}/${encodeURIComponent(transition.id)}/send-test-invites`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ test_recipients: recipients }) }); if (!response.ok) { const body = await response.json().catch(() => ({})); throw new Error(body.detail || "Invite delivery failed."); } renderSchedulerResult(await response.json()); }
  catch (error) { notify(error.message); }
  finally { button.disabled = false; button.textContent = "Send invites"; }
});
document.addEventListener("click", async (event) => { const target = event.target.closest("button") || event.target; if (target.dataset.view) { setView(target.dataset.view); } if (target.dataset.pageView) { pageState[target.dataset.pageView] = Number(target.dataset.pageNumber); render(); } if (target.dataset.productView) { setProductView(target.dataset.productView); } if (target.dataset.workspaceView) { if (target.dataset.workspaceView === "select") { try { await renderTransitionList(); } catch (error) { notify(error.message); } } setWorkspaceView(target.dataset.workspaceView); } if (target.dataset.transitionId) { try { await loadTransition(target.dataset.transitionId); setWorkspaceView("current"); } catch (error) { notify(error.message); } } });
init();