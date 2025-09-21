/* ---------- State ---------- */
let editRow = null;
let editId = null;

/* ---------- Utilities ---------- */
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

async function fetchJSON(url) {
  const res = await fetch(url, {
    headers: { "X-CSRFToken": getCookie("csrftoken") },
  });
  if (!res.ok) throw new Error("Network error");
  return res.json();
}

function setSelectBusy(selectEl, text = "กำลังโหลด…") {
  selectEl.innerHTML = `<option selected hidden value="">${text}</option>`;
  selectEl.disabled = true;
}

function populateSelect(
  selectEl,
  items,
  { placeholder = "เลือก", selected = "" } = {}
) {
  const opts = (Array.isArray(items) ? items : []).map((it) => {
    if (typeof it === "string") return { value: it, text: it };
    if (it && typeof it === "object") {
      const value = it.value ?? it.val ?? it.code ?? "";
      const text = it.text ?? it.label ?? value ?? "";
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

// ===== time utilities =====
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
  const s = hhmmToMinutes(startStr), h = parseFloat(hoursStr || 0);
  if (s === null || !isFinite(h) || h <= 0) return "";
  return minutesToHHMM(s + Math.round(h * 60));
}

function parseHours(raw) {
  if (raw == null) return 0;
  const s = String(raw).replace(/[^\d.]/g, "");
  const v = parseFloat(s);
  return isFinite(v) && v > 0 ? v : 0;
}

/* ---------- 24h display helpers (ใหม่) ---------- */
/** แปลงสตริงเวลา 12 ชั่วโมง (เช่น "8 a.m.", "1 pm", "08:30 PM")
 *  ให้เป็น "HH:mm" ถ้าเป็น HH:mm อยู่แล้ว จะส่งกลับเดิม */
function to24HourFormat(timeStr) {
  if (!timeStr) return timeStr;
  let s = String(timeStr).trim().toLowerCase();

  // กำจัดจุด a.m. / p.m. และช่องว่างซ้ำ
  s = s.replace(/\./g, "").replace(/\s+/g, " ");

  // ถ้าเดิมเป็น HH:mm อยู่แล้ว
  if (/^\d{2}:\d{2}$/.test(s)) return s;

  // จับ "H", "HH", "H:MM" หรือ "HH:MM" + am/pm
  const m = s.match(/^(\d{1,2})(?::(\d{2}))?\s*(a|p)m$/);
  if (!m) return timeStr; // รูปแบบอื่น ๆ ให้คงเดิม

  let h = parseInt(m[1], 10);
  let mm = m[2] ? parseInt(m[2], 10) : 0;
  const ap = m[3];

  if (ap === "p" && h < 12) h += 12;
  if (ap === "a" && h === 12) h = 0;

  return String(h).padStart(2, "0") + ":" + String(mm).padStart(2, "0");
}

/** ไล่แปลง badge เวลาในคอลัมน์ 'เวลาเริ่ม' (td[3]) และ 'เวลาสิ้นสุด' (td[4]) ให้เป็น 24 ชม. */
function normalizeTableTimesTo24h() {
  const rows = document.querySelectorAll("table tbody tr");
  rows.forEach((row) => {
    const tds = row.getElementsByTagName("td");
    [3, 4].forEach((idx) => {
      const cell = tds[idx];
      if (!cell) return;
      const badge = cell.querySelector(".badge");
      if (!badge) return;
      const raw = badge.innerText.trim();
      const conv = to24HourFormat(raw);
      // ปรับให้เป็น HH:mm อย่างเดียว
      badge.innerText = conv;
    });
  });
}

// ===== stop-time helpers (ใหม่) =====
function lockStopSelect(stopSel, end) {
  if (!stopSel || !end) return;
  stopSel.innerHTML = "";
  const opt = document.createElement("option");
  opt.value = end;
  opt.text = end;
  stopSel.appendChild(opt);
  stopSel.value = end;
  stopSel.disabled = true;
}

function unlockStopSelect(stopSel, placeholder = "เลือกเวลาสิ้นสุด") {
  if (!stopSel) return;
  stopSel.disabled = false;
  stopSel.innerHTML = `<option value="">${placeholder}</option>`;
}

function pickOrAppendStop(stopSel, end) {
  if (!end || !stopSel) return;
  let hit = [...stopSel.options].find(o => o.value === end || o.text === end);
  if (!hit) {
    const opt = document.createElement("option");
    opt.value = end;
    opt.text = end;
    stopSel.appendChild(opt);
    hit = opt;
  }
  stopSel.value = end;
}

function computeAndSetStopForCreate() {
  const startSel = document.getElementById('start_time_activity');
  const hoursEl  = document.getElementById('hours_activity');
  const stopSel  = document.getElementById('stop_time_activity');
  if (!startSel || !hoursEl || !stopSel) return;

  const end = calcEnd(startSel.value, parseHours(hoursEl.value));
  if (end) lockStopSelect(stopSel, end);
  else     unlockStopSelect(stopSel, "เลือกเวลาสิ้นสุด");
}

function computeAndSetStopForEdit() {
  const startSel = document.getElementById('edit_start_time_activity');
  const hoursEl  = document.getElementById('edit_hours_activity');
  const stopSel  = document.getElementById('edit_stop_time_activity');
  if (!startSel || !hoursEl || !stopSel) return;

  const end = calcEnd(startSel.value, parseHours(hoursEl.value));
  if (end) lockStopSelect(stopSel, end);
  else     unlockStopSelect(stopSel, "เลือกเวลาสิ้นสุด");
}

/* ---------- Notifications ---------- */
function showNotification(message, type = "info", duration = 4000) {
  const container = document.getElementById("notificationContainer");
  const n = document.createElement("div");
  const typeMap = {
    success: "success",
    error: "error",
    warning: "warning",
    info: "info",
    debug: "info",
  };
  n.className = `notification ${typeMap[type] || "info"}`;
  n.innerHTML = `
    <button class="notification-close" onclick="closeNotification(this)">&times;</button>
    <div>${message}</div>
    <div class="notification-progress"></div>
  `;
  container.appendChild(n);
  setTimeout(() => n.classList.add("show"), 50);
  const bar = n.querySelector(".notification-progress");
  bar.style.width = "100%";
  setTimeout(() => {
    bar.style.transitionDuration = duration + "ms";
    bar.style.width = "0%";
  }, 80);
  setTimeout(
    () => closeNotification(n.querySelector(".notification-close")),
    duration + 120
  );
}
function closeNotification(btn) {
  const n = btn.parentElement;
  n.style.opacity = "0";
  n.style.transform = "translateX(100%)";
  setTimeout(() => n.remove(), 300);
}

/* ---------- Meta loaders (Days / Start / Stop) ---------- */
// สำหรับฟอร์มหลัก
async function loadDaysForCreate() {
  const root = document.getElementById("activity-form");
  const daySel = document.getElementById("day_activity");
  const startSel = document.getElementById("start_time_activity");
  const stopSel = document.getElementById("stop_time_activity");

  setSelectBusy(daySel);
  setSelectBusy(startSel, "เลือกเวลาเริ่ม");
  setSelectBusy(stopSel, "คำนวณอัตโนมัติ");

  try {
    const { days } = await fetchJSON(root.dataset.endpointDays);
    populateSelect(daySel, days, { placeholder: "เลือกวัน" });
  } catch {
    daySel.innerHTML = `<option value="">โหลดวันไม่สำเร็จ</option>`;
    showNotification("โหลดรายการวันไม่สำเร็จ", "error");
  }

  daySel.addEventListener("change", async () => {
    const day = daySel.value;
    setSelectBusy(startSel);
    setSelectBusy(stopSel, "เลือกเวลาเริ่มก่อน");
    if (!day) return;

    try {
      const { start_times } = await fetchJSON(
        root.dataset.endpointStart + encodeURIComponent(day)
      );
      populateSelect(startSel, start_times, { placeholder: "เลือกเวลาเริ่ม" });
    } catch {
      populateSelect(startSel, [], { placeholder: "ไม่มีข้อมูลเวลาเริ่ม" });
      showNotification("โหลดเวลาเริ่มไม่สำเร็จ", "error");
    }
  });

  startSel.addEventListener("change", async () => {
    const day = daySel.value;
    const start = startSel.value;

    unlockStopSelect(stopSel, "กำลังโหลด…");

    if (!day || !start) {
      unlockStopSelect(stopSel, "เลือกเวลาเริ่มก่อน");
      return;
    }

    try {
      const url = root.dataset.endpointStop
        .replace("{day}", encodeURIComponent(day))
        .replace("{start}", encodeURIComponent(start));

      const { stop_times } = await fetchJSON(url);

      populateSelect(stopSel, stop_times, { placeholder: "เลือกเวลาสิ้นสุด" });

      computeAndSetStopForCreate();
    } catch {
      unlockStopSelect(stopSel, "ไม่มีข้อมูลเวลาสิ้นสุด");
      showNotification("โหลดเวลาสิ้นสุดไม่สำเร็จ", "error");
    }
  });
}

// สำหรับ Modal แก้ไข
async function loadDaysForEdit(prefill) {
  const root = document.getElementById("activity-edit");
  const daySel = document.getElementById("edit_day_activity");
  const startSel = document.getElementById("edit_start_time_activity");
  const stopSel = document.getElementById("edit_stop_time_activity");

  setSelectBusy(daySel);
  setSelectBusy(startSel, "เลือกวันก่อน");
  setSelectBusy(stopSel, "เลือกเวลาเริ่มก่อน");

  try {
    const { days } = await fetchJSON(root.dataset.endpointDays);
    populateSelect(daySel, days, {
      placeholder: "เลือกวัน",
      selected: prefill.day,
    });
  } catch {
    daySel.innerHTML = `<option value="">โหลดวันไม่สำเร็จ</option>`;
  }

  // โหลด start ตามวัน (ใช้ค่า prefill.start ถ้ามี)
  if (daySel.value) {
    try {
      const { start_times } = await fetchJSON(
        root.dataset.endpointStart + encodeURIComponent(daySel.value)
      );
      populateSelect(startSel, start_times, {
        placeholder: "เลือกเวลาเริ่ม",
        selected: prefill.start,
      });
    } catch {
      populateSelect(startSel, [], { placeholder: "ไม่มีข้อมูลเวลาเริ่ม" });
    }
  }

  // โหลด stop ตามวัน+start (ใช้ค่า prefill.stop ถ้ามี)
  if (daySel.value && startSel.value) {
    try {
      const url = root.dataset.endpointStop
        .replace("{day}", encodeURIComponent(daySel.value))
        .replace("{start}", encodeURIComponent(startSel.value));
      const { stop_times } = await fetchJSON(url);
      populateSelect(stopSel, stop_times, {
        placeholder: "เลือกเวลาสิ้นสุด",
        selected: prefill.stop,
      });
      // >>> คำนวณครั้งแรกหลัง populate
      computeAndSetStopForEdit();
    } catch {
      populateSelect(stopSel, [], { placeholder: "ไม่มีข้อมูลเวลาสิ้นสุด" });
    }
  }

  // รีแคสเคดเมื่อมีการเปลี่ยนใน modal
  daySel.onchange = async () => {
    const day = daySel.value;
    setSelectBusy(startSel);
    setSelectBusy(stopSel, "เลือกเวลาเริ่มก่อน");
    if (!day) return;
    try {
      const { start_times } = await fetchJSON(
        root.dataset.endpointStart + encodeURIComponent(day)
      );
      populateSelect(startSel, start_times, { placeholder: "เลือกเวลาเริ่ม" });
    } catch {
      populateSelect(startSel, [], { placeholder: "ไม่มีข้อมูลเวลาเริ่ม" });
    }
  };

  startSel.onchange = async () => {
    const day = daySel.value;
    const start = startSel.value;
    setSelectBusy(stopSel);
    if (!day || !start) {
      setSelectBusy(stopSel, "เลือกเวลาเริ่มก่อน");
      return;
    }
    try {
      const url = root.dataset.endpointStop
        .replace("{day}", encodeURIComponent(day))
        .replace("{start}", encodeURIComponent(start));
      const { stop_times } = await fetchJSON(url);
      populateSelect(stopSel, stop_times, { placeholder: "เลือกเวลาสิ้นสุด" });
      // >>> คำนวณใหม่ทุกครั้งที่เปลี่ยน start
      computeAndSetStopForEdit();
    } catch {
      populateSelect(stopSel, [], { placeholder: "ไม่มีข้อมูลเวลาสิ้นสุด" });
    }
  };
}

/* ---------- CRUD ---------- */
function addActivity() {
  const act_name_activity = document
    .getElementById("act_name_activity")
    .value.trim();
  const day_activity = document.getElementById("day_activity").value;
  const hours_activity = document.getElementById("hours_activity").value;
  const start_time_activity = document.getElementById(
    "start_time_activity"
  ).value;
  const stop_time_activity =
    document.getElementById("stop_time_activity").value;
  const hours_activity_raw = document.getElementById("hours_activity").value;

  if (!act_name_activity)
    return showNotification("กรุณากรอกชื่อกิจกรรม", "warning");
  if (!day_activity) return showNotification("กรุณาเลือกวัน", "warning");
  if (!start_time_activity)
    return showNotification("กรุณาเลือกเวลาเริ่ม", "warning");
  if (!stop_time_activity)
    return showNotification("กรุณาเลือกเวลาสิ้นสุด", "warning");

  fetch("/api/activity/add/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCookie("csrftoken"),
    },
    body: JSON.stringify({
      act_name_activity,
      day_activity,
      hours_activity: Number(parseHours(hours_activity_raw)),
      start_time_activity,
      stop_time_activity,
    }),
  })
    .then((r) => r.json())
    .then((data) => {
      if (data.status === "success") {
        showNotification("✅ เพิ่มกิจกรรมเรียบร้อยแล้ว", "success");
        location.reload();
      } else {
        showNotification("เกิดข้อผิดพลาด: " + (data.message || ""), "error");
      }
    })
    .catch(() => showNotification("เกิดข้อผิดพลาดในการเพิ่มข้อมูล", "error"));
}

function confirmDelete(button) {
  if (!confirm("คุณแน่ใจหรือไม่ว่าต้องการลบรายการนี้?")) return;
  const row = button.closest("tr");
  const id = row.getAttribute("data-id");

  fetch(`/api/activity/delete/${id}/`, {
    method: "DELETE",
    headers: { "X-CSRFToken": getCookie("csrftoken") },
  })
    .then((r) => r.json())
    .then((data) => {
      if (data.status === "success") {
        row.remove();
        showNotification("✅ ลบข้อมูลเรียบร้อยแล้ว", "success");
      } else {
        showNotification("เกิดข้อผิดพลาดในการลบข้อมูล", "error");
      }
    })
    .catch(() => showNotification("เกิดข้อผิดพลาดในการลบข้อมูล", "error"));
}

function openEditModal(button) {
  const row = button.closest("tr");
  editRow = row;
  editId = row.getAttribute("data-id");

  const cells = row.getElementsByTagName("td");
  const prefill = {
    name: cells[0].innerText.trim(),
    day: cells[1].querySelector(".badge").innerText.trim(),
    hours: cells[2].querySelector(".badge").innerText.trim(),
    start: cells[3].querySelector(".badge").innerText.trim(),
    stop: cells[4].querySelector(".badge").innerText.trim(),
  };

  document.getElementById("edit_act_name_activity").value = prefill.name;
  document.getElementById("edit_hours_activity").value = parseHours(prefill.hours);

  // โหลด dropdown ของ modal ตามค่าที่แถวปัจจุบันถืออยู่
  loadDaysForEdit({
    day: prefill.day,
    start: prefill.start,
    stop: prefill.stop,
  });

  // คำนวณ stop ครั้งแรกหลัง modal มีค่าแล้ว
  setTimeout(computeAndSetStopForEdit, 0);

  new bootstrap.Modal(document.getElementById("editModal")).show();
}

function saveEdit() {
  const act_name_activity = document
    .getElementById("edit_act_name_activity")
    .value.trim();
  const day_activity = document.getElementById("edit_day_activity").value;
  const hours_activity = document.getElementById("edit_hours_activity").value;
  const start_time_activity = document.getElementById(
    "edit_start_time_activity"
  ).value;
  const stop_time_activity = document.getElementById(
    "edit_stop_time_activity"
  ).value;
  const hours_activity_raw = document.getElementById("edit_hours_activity").value;

  if (
    !act_name_activity ||
    !day_activity ||
    !start_time_activity ||
    !stop_time_activity
  ) {
    return showNotification("กรุณากรอกข้อมูลให้ครบถ้วน", "warning");
  }

  fetch(`/api/activity/update/${editId}/`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCookie("csrftoken"),
    },
    body: JSON.stringify({
      act_name_activity,
      day_activity,
      hours_activity: Number(parseHours(hours_activity_raw)),
      start_time_activity,
      stop_time_activity,
    }),
  })
    .then((r) => r.json())
    .then((data) => {
      if (data.status === "success") {
        showNotification("✅ แก้ไขข้อมูลเรียบร้อยแล้ว", "success");
        bootstrap.Modal.getInstance(
          document.getElementById("editModal")
        ).hide();
        location.reload();
      } else {
        showNotification("เกิดข้อผิดพลาดในการแก้ไขข้อมูล", "error");
      }
    })
    .catch(() => showNotification("เกิดข้อผิดพลาดในการแก้ไขข้อมูล", "error"));
}

function refreshData() {
  location.reload();
}

/* ---------- Init ---------- */
window.addEventListener("load", () => {
  showNotification("ยินดีต้อนรับสู่หน้าจัดการกิจกรรม", "info");
  loadDaysForCreate(); // โหลด dropdown สำหรับฟอร์มสร้างใหม่

  // บังคับให้แสดงเวลาในตารางเป็น 24 ชั่วโมงทันทีหลังโหลด
  normalizeTableTimesTo24h();

  // คำนวณอัตโนมัติเมื่อเปลี่ยน start หรือ hours (หน้าฟอร์มสร้าง)
  document.getElementById('start_time_activity')
    ?.addEventListener('change', computeAndSetStopForCreate);
  document.getElementById('hours_activity')
    ?.addEventListener('input', computeAndSetStopForCreate);

  // สำหรับ modal: เผื่อ element มีอยู่แล้ว (บางธีม preload)
  document.getElementById('edit_start_time_activity')
    ?.addEventListener('change', computeAndSetStopForEdit);
  document.getElementById('edit_hours_activity')
    ?.addEventListener('input', computeAndSetStopForEdit);

  // Django messages (ถ้ามี)
  if (Array.isArray(window.__DJANGO_MESSAGES__)) {
    window.__DJANGO_MESSAGES__.forEach((m) =>
      showNotification(m.text, m.level || "info")
    );
  }
});

// ===== ลบกิจกรรมทั้งหมด =====
function deleteAllActivities() {
  if (!confirm("คุณแน่ใจหรือไม่ว่าต้องการลบกิจกรรมทั้งหมด?")) return;

  fetch("/api/activity/delete-all/", {
    method: "DELETE",
    headers: { "X-CSRFToken": getCookie("csrftoken") },
  })
    .then((r) => r.json())
    .then((data) => {
      if (data.status === "success") {
        showNotification("✅ ลบกิจกรรมทั้งหมดเรียบร้อยแล้ว", "success");
        location.reload();
      } else {
        showNotification("เกิดข้อผิดพลาด: " + (data.message || ""), "error");
      }
    })
    .catch(() =>
      showNotification("เกิดข้อผิดพลาดในการลบกิจกรรมทั้งหมด", "error")
    );
}

