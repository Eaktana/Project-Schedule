// weekactivity.js — subject-style, fixed start free / stop locked + flash toast

/* ---------- State ---------- */
let editRow = null;
let editId = null;
let pendingDeleteId = null;

/* ---------- Elements / Modals ---------- */
const delModalEl    = document.getElementById("confirmDeleteActivityModal");
const delAllModalEl = document.getElementById("confirmDeleteAllActivityModal");
const delNameEl     = document.getElementById("del_activity_name");
const btnConfirmDel = document.getElementById("btnConfirmDeleteActivity");
const btnConfirmAll = document.getElementById("btnConfirmDeleteAllActivity");

const bsDel    = delModalEl    ? new bootstrap.Modal(delModalEl)    : null;
const bsDelAll = delAllModalEl ? new bootstrap.Modal(delAllModalEl) : null;

/* ---------- Utils ---------- */
function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== "") {
    const cookies = document.cookie.split(";");
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === name + "=") {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

async function fetchJSON(url, options = {}) {
  const res = await fetch(url, {
    ...options,
    headers: { Accept: "application/json", ...(options.headers || {}) },
  });
  if (!res.ok) {
    try {
      const j = await res.json();
      throw new Error(j?.message || j?.detail || `HTTP ${res.status}`);
    } catch {
      throw new Error(`HTTP ${res.status}`);
    }
  }
  const ct = res.headers.get("content-type") || "";
  return ct.includes("application/json") ? res.json() : res.text();
}

function populateSelect(selectEl, items, { placeholder = "เลือก", selected = "" } = {}) {
  if (!selectEl) return;
  const opts = (Array.isArray(items) ? items : []).map((it) => {
    if (typeof it === "string") return { value: it, text: it };
    if (it && typeof it === "object") {
      const value = it.value ?? it.val ?? it.code ?? it.id ?? "";
      const text  = it.text  ?? it.label ?? value ?? "";
      return { value, text };
    }
    const v = String(it ?? "");
    return { value: v, text: v };
  });
  const html = ['<option value="">' + placeholder + "</option>"]
    .concat(opts.map((o) => `<option value="${o.value}">${o.text}</option>`))
    .join("");
  selectEl.innerHTML = html;
  selectEl.disabled = false;
  if (selected) {
    const hit = opts.find((o) => o.value === selected || o.text === selected);
    if (hit) selectEl.value = hit.value;
  }
}

// time helpers
function hhmmToMinutes(hhmm) {
  if (!hhmm) return null;
  const [h, m] = hhmm.split(":").map(Number);
  return isNaN(h) || isNaN(m) ? null : h * 60 + m;
}
function minutesToHHMM(mins) {
  mins = ((mins % 1440) + 1440) % 1440;
  const h = String(Math.floor(mins / 60)).padStart(2, "0");
  const m = String(mins % 60).padStart(2, "0");
  return `${h}:${m}`;
}
function calcEnd(startStr, hoursStr) {
  const s = hhmmToMinutes(startStr), h = parseFloat(String(hoursStr || 0).replace(/[^\d.]/g, ""));
  if (s === null || !isFinite(h) || h <= 0) return "";
  return minutesToHHMM(s + Math.round(h * 60));
}
function parseHours(raw) {
  if (raw == null) return 0;
  const s = String(raw).replace(/[^\d.]/g, "");
  const v = parseFloat(s);
  return isFinite(v) && v > 0 ? v : 0;
}

/* ---------- Stop-time: locked always ---------- */
function lockStopSelect(stopSel, end) {
  if (!stopSel) return;
  stopSel.innerHTML = end ? `<option value="${end}">${end}</option>`
                          : `<option value="">คำนวณอัตโนมัติ</option>`;
  stopSel.value = end || "";
  stopSel.disabled = true; // locked always
}
function unlockStopSelect(stopSel, placeholder = "คำนวณอัตโนมัติ") {
  if (!stopSel) return;
  stopSel.disabled = true; // never unlock
  stopSel.innerHTML = `<option value="">${placeholder}</option>`;
}
function computeAndSetStopForCreate() {
  const startSel = document.getElementById('start_time_activity');
  const hoursEl  = document.getElementById('hours_activity');
  const stopSel  = document.getElementById('stop_time_activity');
  if (!startSel || !hoursEl || !stopSel) return;
  const end = calcEnd(startSel.value, hoursEl.value);
  lockStopSelect(stopSel, end || "");
}
function computeAndSetStopForEdit() {
  const startSel = document.getElementById('edit_start_time_activity');
  const hoursEl  = document.getElementById('edit_hours_activity');
  const stopSel  = document.getElementById('edit_stop_time_activity');
  if (!startSel || !hoursEl || !stopSel) return;
  const end = calcEnd(startSel.value, hoursEl.value);
  lockStopSelect(stopSel, end || "");
}

/* ---------- Notifications (Subject-style) ---------- */
function escapeHtml(s) {
  return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/\"/g, "&quot;").replace(/'/g, "&#039;");
}
function showToast(kind, title, message) {
  let toastHost = document.getElementById("toastHost");
  if (!toastHost) {
    toastHost = document.createElement("div");
    toastHost.id = "toastHost";
    toastHost.className = "toast-container position-fixed top-0 end-0 p-3";
    toastHost.style.zIndex = "2000";
    document.body.appendChild(toastHost);
  }
  const bgMap = {
    success: "bg-success text-white",
    warning: "bg-warning",
    danger:  "bg-danger text-white",
    info:    "bg-primary text-white",
  };
  const headerClass = bgMap[kind] || "bg-dark text-white";
  const el = document.createElement("div");
  el.className = "toast align-items-center border-0 shadow overflow-hidden";
  el.style.borderRadius = "12px";
  el.setAttribute("role", "alert");
  el.setAttribute("aria-live", "assertive");
  el.setAttribute("aria-atomic", "true");
  el.innerHTML = `
    <div class="toast-header ${headerClass}">
      <strong class="me-auto">${escapeHtml(title || "")}</strong>
      <button type="button" class="btn-close btn-close-white ms-2 mb-1" data-bs-dismiss="toast" aria-label="Close"></button>
    </div>
    <div class="toast-body">${escapeHtml(message || "")}</div>`;
  toastHost.appendChild(el);
  new bootstrap.Toast(el, { delay: 3500, autohide: true }).show();
}
// alias
function showNotification(message, type = "info", title = null) {
  const map = { success: "success", warning: "warning", error: "danger", info: "info", debug: "info" };
  const defaultTitles = { success: "สำเร็จ", warning: "คำเตือน", danger: "ผิดพลาด", info: "แจ้งเตือน" };
  const kind = map[type] || "info";
  showToast(kind, title ?? defaultTitles[kind] ?? "แจ้งเตือน", message);
}

/* ---------- Flash toast across reload ---------- */
function flashToast(msg, type = "info", title = null) {
  try {
    sessionStorage.setItem("flashToast", JSON.stringify({ msg, type, title, t: Date.now() }));
  } catch {}
}
function showFlashToastIfAny() {
  try {
    const raw = sessionStorage.getItem("flashToast");
    if (!raw) return;
    sessionStorage.removeItem("flashToast");
    const { msg, type, title } = JSON.parse(raw);
    showNotification(msg, type || "info", title);
  } catch {}
}

/* ---------- Meta loaders ---------- */
async function loadDaysForCreate() {
  const root     = document.getElementById("activity-form");
  const daySel   = document.getElementById("day_activity");
  const startSel = document.getElementById("start_time_activity");
  const stopSel  = document.getElementById("stop_time_activity");

  // โหลดวัน
  try {
    const data = await fetchJSON(root.dataset.endpointDays);
    populateSelect(daySel, data.days || [], { placeholder: "เลือกวัน" });
  } catch {
    populateSelect(daySel, [], { placeholder: "เลือกวัน" });
    showNotification("โหลดรายการวันไม่สำเร็จ", "error");
  }

  // เวลาเริ่ม: เปิดตลอด ไม่มีสถานะโหลด
  populateSelect(startSel, [], { placeholder: "เลือกเวลาเริ่ม" });
  startSel.disabled = false;

  // เปลี่ยนวัน → โหลดตัวเลือกเวลาเริ่มใหม่ (แต่ dropdown ยังเปิดได้)
  daySel.addEventListener("change", async () => {
    const day = daySel.value;
    if (!day) {
      populateSelect(startSel, [], { placeholder: "เลือกเวลาเริ่ม" });
      lockStopSelect(stopSel, "");
      return;
    }
    try {
      const data = await fetchJSON(root.dataset.endpointStart + encodeURIComponent(day));
      populateSelect(startSel, data.start_times || [], { placeholder: "เลือกเวลาเริ่ม" });
    } catch {
      populateSelect(startSel, [], { placeholder: "เลือกเวลาเริ่ม" });
    }
    // เปลี่ยนวันแล้วให้คำนวณใหม่ (กรณี start/hours มีค่า)
    computeAndSetStopForCreate();
  });

  // เปลี่ยนเวลาเริ่ม/จำนวนชั่วโมง → คำนวณสิ้นสุด (ไม่เรียก API stop)
  startSel.addEventListener("change", computeAndSetStopForCreate);
  document.getElementById('hours_activity')?.addEventListener('input', computeAndSetStopForCreate);
}

async function loadDaysForEdit(prefill) {
  const root     = document.getElementById("activity-edit");
  const daySel   = document.getElementById("edit_day_activity");
  const startSel = document.getElementById("edit_start_time_activity");
  const stopSel  = document.getElementById("edit_stop_time_activity");

  // วัน
  try {
    const data = await fetchJSON(root.dataset.endpointDays);
    populateSelect(daySel, data.days || [], { placeholder: "เลือกวัน", selected: prefill.day });
  } catch {
    populateSelect(daySel, [], { placeholder: "เลือกวัน" });
  }

  // เวลาเริ่ม (เปิดตลอด)
  try {
    if (daySel.value) {
      const data = await fetchJSON(root.dataset.endpointStart + encodeURIComponent(daySel.value));
      populateSelect(startSel, data.start_times || [], { placeholder: "เลือกเวลาเริ่ม", selected: prefill.start });
    } else {
      populateSelect(startSel, [], { placeholder: "เลือกเวลาเริ่ม" });
    }
  } catch {
    populateSelect(startSel, [], { placeholder: "เลือกเวลาเริ่ม" });
  }
  startSel.disabled = false;

  // คำนวณสิ้นสุดครั้งแรก
  computeAndSetStopForEdit();

  // เปลี่ยนวัน → โหลดเวลาเริ่มใหม่
  daySel.onchange = async () => {
    const day = daySel.value;
    if (!day) { populateSelect(startSel, [], { placeholder: "เลือกเวลาเริ่ม" }); computeAndSetStopForEdit(); return; }
    try {
      const data = await fetchJSON(root.dataset.endpointStart + encodeURIComponent(day));
      populateSelect(startSel, data.start_times || [], { placeholder: "เลือกเวลาเริ่ม" });
    } catch {
      populateSelect(startSel, [], { placeholder: "เลือกเวลาเริ่ม" });
    }
    computeAndSetStopForEdit();
  };

  // เปลี่ยน start / hours → คำนวณสิ้นสุด
  startSel.onchange = computeAndSetStopForEdit;
  document.getElementById('edit_hours_activity')?.addEventListener('input', computeAndSetStopForEdit);
}

/* ---------- CRUD ---------- */
function addActivity(e) {
  e?.preventDefault?.();
  const name  = document.getElementById("act_name_activity").value.trim();
  const day   = document.getElementById("day_activity").value;
  const hours = parseHours(document.getElementById("hours_activity").value);
  const start = document.getElementById("start_time_activity").value;
  const stop  = document.getElementById("stop_time_activity").value;

  if (!name)  return showNotification("กรุณากรอกชื่อกิจกรรม", "warning");
  if (!day)   return showNotification("กรุณาเลือกวัน", "warning");
  if (!start) return showNotification("กรุณาเลือกเวลาเริ่ม", "warning");
  if (!stop)  return showNotification("กรุณาเลือกเวลาสิ้นสุด", "warning");

  fetch("/api/activity/add/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCookie("csrftoken"),
      Accept: "application/json",
    },
    body: JSON.stringify({
      act_name_activity: name,
      day_activity: day,
      hours_activity: Number(hours),
      start_time_activity: start,
      stop_time_activity: stop,
    }),
  })
    .then((r) => r.json())
    .then((data) => {
      if (data.status === "success") {
        flashToast("เพิ่มกิจกรรมเรียบร้อยแล้ว", "success", "เพิ่มสำเร็จ");
        location.reload();
      } else {
        showNotification("เกิดข้อผิดพลาด: " + (data.message || ""), "error");
      }
    })
    .catch(() => showNotification("เกิดข้อผิดพลาดในการเพิ่มข้อมูล", "error"));
}

function openEditModal(button) {
  const row = button.closest("tr");
  editRow = row;
  editId = row.getAttribute("data-id");

  const cells = row.getElementsByTagName("td");
  const prefill = {
    name:  cells[0]?.innerText.trim(),
    day:   cells[1]?.querySelector(".badge")?.innerText.trim() || cells[1]?.innerText.trim(),
    hours: cells[2]?.querySelector(".badge")?.innerText.trim() || cells[2]?.innerText.trim(),
    start: cells[3]?.querySelector(".badge")?.innerText.trim() || cells[3]?.innerText.trim(),
    stop:  cells[4]?.querySelector(".badge")?.innerText.trim() || cells[4]?.innerText.trim(),
  };

  document.getElementById("edit_act_name_activity").value = prefill.name || "";
  document.getElementById("edit_hours_activity").value   = parseHours(prefill.hours);

  loadDaysForEdit({ day: prefill.day, start: prefill.start, stop: prefill.stop });
  setTimeout(computeAndSetStopForEdit, 0);

  new bootstrap.Modal(document.getElementById("editModal")).show();
}

function saveEdit() {
  const name  = document.getElementById("edit_act_name_activity").value.trim();
  const day   = document.getElementById("edit_day_activity").value;
  const hours = parseHours(document.getElementById("edit_hours_activity").value);
  const start = document.getElementById("edit_start_time_activity").value;
  const stop  = document.getElementById("edit_stop_time_activity").value;

  if (!name || !day || !start || !stop) {
    return showNotification("กรุณากรอกข้อมูลให้ครบถ้วน", "warning");
  }

  fetch(`/api/activity/update/${editId}/`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCookie("csrftoken"),
      Accept: "application/json",
    },
    body: JSON.stringify({
      act_name_activity: name,
      day_activity: day,
      hours_activity: Number(hours),
      start_time_activity: start,
      stop_time_activity: stop,
    }),
  })
    .then((r) => r.json())
    .then((data) => {
      if (data.status === "success") {
        flashToast("แก้ไขข้อมูลเรียบร้อยแล้ว", "success", "แก้ไขสำเร็จ");
        bootstrap.Modal.getInstance(document.getElementById("editModal")).hide();
        location.reload();
      } else {
        showNotification("เกิดข้อผิดพลาดในการแก้ไขข้อมูล", "error");
      }
    })
    .catch(() => showNotification("เกิดข้อผิดพลาดในการแก้ไขข้อมูล", "error"));
}

/* ---------- Delete (Subject-style modal) ---------- */
function confirmDelete(button) {
  const row  = button.closest("tr");
  const id   = row.getAttribute("data-id");
  const name = row.querySelector("td")?.innerText?.trim() || "กิจกรรม";

  if (bsDel && btnConfirmDel) {
    pendingDeleteId = id;
    if (delNameEl) delNameEl.textContent = name;
    bsDel.show();

    const handler = async () => {
      try {
        btnConfirmDel.disabled = true;
        const r = await fetch(`/api/activity/delete/${pendingDeleteId}/`, {
          method: "DELETE",
          headers: { "X-CSRFToken": getCookie("csrftoken"), Accept: "application/json" },
        });
        const data = await r.json();
        if (data.status === "success") {
          flashToast("ลบข้อมูลเรียบร้อยแล้ว", "success", "ลบสำเร็จ");
          bsDel.hide();
          location.reload();
        } else {
          showNotification("เกิดข้อผิดพลาดในการลบข้อมูล", "error", "ลบไม่สำเร็จ");

        }
      } catch {
        showNotification("เกิดข้อผิดพลาดในการลบข้อมูล", "error", "ลบไม่สำเร็จ");
      } finally {
        btnConfirmDel.disabled = false;
        btnConfirmDel.removeEventListener("click", handler);
        pendingDeleteId = null;
      }
    };
    btnConfirmDel.addEventListener("click", handler);
  } else {
    if (!confirm("คุณแน่ใจหรือไม่ว่าต้องการลบรายการนี้?")) return;
    fetch(`/api/activity/delete/${id}/`, {
      method: "DELETE",
      headers: { "X-CSRFToken": getCookie("csrftoken"), Accept: "application/json" },
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.status === "success") {
          flashToast("ลบข้อมูลเรียบร้อยแล้ว", "success");
          location.reload();
        } else {
          showNotification("เกิดข้อผิดพลาดในการลบข้อมูล", "error", "ลบไม่สำเร็จ");
        }
      })
      .catch(() => showNotification("เกิดข้อผิดพลาดในการลบข้อมูล", "error", "ลบไม่สำเร็จ"));
  }
}

function deleteAllActivities() {
  if (bsDelAll && btnConfirmAll) {
    bsDelAll.show();
    const handler = async () => {
      try {
        btnConfirmAll.disabled = true;
        const r = await fetch("/api/activity/delete-all/", {
          method: "DELETE",
          headers: { "X-CSRFToken": getCookie("csrftoken"), Accept: "application/json" },
        });
        const data = await r.json();
        if (data.status === "success") {
          flashToast("ลบกิจกรรมทั้งหมดเรียบร้อยแล้ว", "success", "ลบทั้งหมดสำเร็จ");
          bsDelAll.hide();
          location.reload();
        } else {
          showNotification("เกิดข้อผิดพลาด: " + (data.message || ""), "error");
        }
      } catch {
        showNotification("เกิดข้อผิดพลาดในการลบกิจกรรมทั้งหมด", "error");
      } finally {
        btnConfirmAll.disabled = false;
        btnConfirmAll.removeEventListener("click", handler);
      }
    };
    btnConfirmAll.addEventListener("click", handler);
  } else {
    if (!confirm("คุณแน่ใจหรือไม่ว่าต้องการลบกิจกรรมทั้งหมด?")) return;
    fetch("/api/activity/delete-all/", {
      method: "DELETE",
      headers: { "X-CSRFToken": getCookie("csrftoken"), Accept: "application/json" },
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.status === "success") {
          flashToast("ลบกิจกรรมทั้งหมดเรียบร้อยแล้ว", "success");
          location.reload();
        } else {
          showNotification("เกิดข้อผิดพลาด: " + (data.message || ""), "error");
        }
      })
      .catch(() => showNotification("เกิดข้อผิดพลาดในการลบกิจกรรมทั้งหมด", "error"));
  }
}

/* ---------- Init ---------- */
(function boot() {
  // แสดง flash toast หลังรีเฟรช (ไม่ต้องรอ window.load)
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", showFlashToastIfAny);
  } else {
    showFlashToastIfAny();
  }

  // โหลด dropdowns
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", loadDaysForCreate);
  } else {
    loadDaysForCreate();
  }

  // bind คำนวณ stop อัตโนมัติ
  const binders = () => {
    document.getElementById('start_time_activity')?.addEventListener('change', computeAndSetStopForCreate);
    document.getElementById('hours_activity')?.addEventListener('input',  computeAndSetStopForCreate);
    document.getElementById('edit_start_time_activity')?.addEventListener('change', computeAndSetStopForEdit);
    document.getElementById('edit_hours_activity')?.addEventListener('input',  computeAndSetStopForEdit);
  };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", binders);
  } else {
    binders();
  }
})();

/* ---------- Expose for HTML onclick ---------- */
window.addActivity          = addActivity;
window.openEditModal        = openEditModal;
window.saveEdit             = saveEdit;
window.confirmDelete        = confirmDelete;
window.deleteAllActivities  = deleteAllActivities;
