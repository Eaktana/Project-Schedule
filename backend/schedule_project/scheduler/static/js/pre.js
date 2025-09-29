// ===== helper: select existing element by first found id =====
function pickEl() {
  for (const id of arguments) {
    const el = document.getElementById(id);
    if (el) return el;
  }
  return null;
}

// ===== helper: set selected value on <select> =====
function setSelectValue(sel, val) {
  if (!sel) return;
  const hit = [...sel.options].find((o) => o.value === val || o.text === val);
  if (hit) sel.value = hit.value;
  else if (val !== undefined && val !== null && String(val).trim() !== "") {
    const opt = document.createElement("option");
    opt.value = val;
    opt.text = val;
    sel.appendChild(opt);
    sel.value = val;
  }
}

// แปลงเลข -> สตริงกลุ่มเรียน เช่น "1" => "sec1"
function composeSectionFromNum(n) {
  const s = String(n || "").trim();
  return s ? `sec${s}` : "";
}

// แปลงสตริงกลุ่มเรียน -> เลข เช่น "sec 12" => "12"
function parseSectionToNum(secText) {
  if (secText == null) return "";
  const m = String(secText).trim().match(/^sec\s*(\d+)$/i);
  return m ? m[1] : "";
}

// ----- Delete modals (Pre) -----
let pendingDeleteId = null;

const delModalEl    = document.getElementById('confirmDeletePreModal');
const delAllModalEl = document.getElementById('confirmDeleteAllPreModal');
const delNameEl     = document.getElementById('del_pre_name');
const btnConfirmDel = document.getElementById('btnConfirmDeletePre');
const btnConfirmAll = document.getElementById('btnConfirmDeleteAllPre');

const bsDel    = delModalEl    ? new bootstrap.Modal(delModalEl)    : null;
const bsDelAll = delAllModalEl ? new bootstrap.Modal(delAllModalEl) : null;

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
  const s = hhmmToMinutes(startStr),
    h = parseFloat(hoursStr || 0);
  if (s === null || !isFinite(h) || h <= 0) return "";
  return minutesToHHMM(s + Math.round(h * 60));
}

// ===== notification system =====
function escapeHtml(s){
  return String(s ?? "").replace(/&/g,"&amp;").replace(/</g,"&lt;")
    .replace(/>/g,"&gt;").replace(/\"/g,"&quot;").replace(/'/g,"&#039;");
}

function showToast(kind, title, message){
  const host = document.getElementById("toastHost");
  if(!host) return alert(message || title || "");
  const bg = { success:"bg-success text-white", warning:"bg-warning",
               danger:"bg-danger text-white", info:"bg-primary text-white" };
  const headerClass = bg[kind] || "bg-dark text-white";

  const el = document.createElement("div");
  el.className = "toast align-items-center border-0 shadow overflow-hidden";
  el.style.borderRadius = "12px";
  el.setAttribute("role","alert");
  el.setAttribute("aria-live","assertive");
  el.setAttribute("aria-atomic","true");
  el.innerHTML = `
    <div class="toast-header ${headerClass}">
      <strong class="me-auto">${escapeHtml(title || "")}</strong>
      <button type="button" class="btn-close btn-close-white ms-2 mb-1"
              data-bs-dismiss="toast" aria-label="Close"></button>
    </div>
    <div class="toast-body">${escapeHtml(message || "")}</div>`;
  host.appendChild(el);
  new bootstrap.Toast(el, { delay: 3500, autohide: true }).show();
}

/* ให้เรียกชื่อเดิม showNotification ได้เหมือนหน้าอื่น */
function showNotification(message, type = "info", title = null){
  const map = { success:"success", warning:"warning", error:"danger", info:"info", debug:"info" };
  const defaults = { success:"สำเร็จ", warning:"คำเตือน", danger:"ผิดพลาด", info:"แจ้งเตือน" };
  const kind = map[type] || "info";
  showToast(kind, title ?? defaults[kind] ?? "แจ้งเตือน", message);
}

/* flashToast สำหรับกรณี reload แล้วอยากให้ toast โผล่หลังโหลดเสร็จ */
function flashToast(msg, type = "info", title = null){
  try { sessionStorage.setItem("flashToast", JSON.stringify({ msg, type, title })); } catch {}
}
function showFlashToastIfAny(){
  try {
    const raw = sessionStorage.getItem("flashToast");
    if (!raw) return;
    sessionStorage.removeItem("flashToast");
    const { msg, type, title } = JSON.parse(raw);
    showNotification(msg, type || "info", title);
  } catch {}
}
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", showFlashToastIfAny);
} else {
  showFlashToastIfAny();
}

// ===== csrf helper =====
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

// ===== AJAX helper to populate selects =====
async function populateSelect(url, selectId, mapItem) {
  const sel = document.getElementById(selectId);
  if (!sel) return;
  const prev = sel.value;
  sel.innerHTML = '<option value="">กำลังโหลด...</option>';
  try {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const payload = await r.json();
    const results = Array.isArray(payload)
      ? payload
      : payload.results ||
        payload.items ||
        payload.days ||
        payload.start_times ||
        payload.stop_times ||
        [];
    sel.innerHTML = '<option value="">เลือก</option>';
    (results || []).forEach((item) => {
      const opt = document.createElement("option");
      const { value, label, dataset } = mapItem(item);
      opt.value = value;
      opt.textContent = label;
      if (dataset)
        Object.entries(dataset).forEach(([k, v]) => (opt.dataset[k] = v));
      sel.appendChild(opt);
    });
    if (prev) setSelectValue(sel, prev);
  } catch (e) {
    console.error(`Populate ${selectId} fail:`, e);
    sel.innerHTML = '<option value="">โหลดไม่สำเร็จ</option>';
  }
}

// =========== กรองห้อง by เอก ===================
function filterRoomOptions(roomSelectId, wantedTypeName) {
  const sel = document.getElementById(roomSelectId);
  if (!sel) return;

  if (!wantedTypeName) {
    [...sel.options].forEach((o) => (o.hidden = false));
    sel.value = "";
    return;
  }

  let firstVisible = null;
  [...sel.options].forEach((o) => {
    const roomType =
      (o.dataset && (o.dataset.typeName || o.dataset.typename)) ||
      o.getAttribute?.("data-type-name") ||
      "";
    const ok = roomType === wantedTypeName;
    o.hidden = !ok;
    if (ok && !firstVisible && o.value) firstVisible = o;
  });

  sel.value = firstVisible ? firstVisible.value : "";
}

// ===== sync subject code/name =====
function wireSubjectCodeNameSync(codeSelId, nameSelId) {
  const codeSel = document.getElementById(codeSelId);
  const nameSel = document.getElementById(nameSelId);
  if (!codeSel || !nameSel) return;

  codeSel.addEventListener("change", () => {
    const codeOpt = codeSel.selectedOptions[0];
    if (!codeOpt) return;
    const sid = codeOpt.dataset.sid;
    if (!sid) return;
    const match = [...nameSel.options].find((o) => o.dataset.sid === sid);
    if (match) nameSel.value = match.value;
  });

  nameSel.addEventListener("change", () => {
    const nameOpt = nameSel.selectedOptions[0];
    if (!nameOpt) return;
    const sid = nameOpt.dataset.sid;
    if (!sid) return;
    const match = [...codeSel.options].find((o) => o.dataset.sid === sid);
    if (match) codeSel.value = match.value;
  });
}

// ===== CRUD functions =====
function addPreSchedule() {
  const sectionNum = (document.getElementById('pre_section_num').value || '').trim();
  const section_pre = composeSectionFromNum(sectionNum);

  if (!section_pre) {
    showNotification('กรุณากรอกกลุ่มเรียน (ตัวเลขหลัง sec)', 'warning');
    return;
  }

  const payload = {
    teacher_name_pre: document.getElementById("teacher_name_pre").value,
    subject_code_pre: document.getElementById("subject_code_pre").value,
    subject_name_pre: document.getElementById("subject_name_pre").value,
    room_type_pre: document.getElementById("subject_type_pre").value,
    type_pre: document.getElementById("type_pre").value,
    student_group_name_pre: document.getElementById("student_group_pre").value,
    hours_pre: Number(document.getElementById("hours_pre").value || 0),
    section_pre,
    day_pre: document.getElementById("day_pre").value,
    start_time_pre: document.getElementById("start_time_pre").value,
    stop_time_pre: document.getElementById("stop_time_pre").value,
    room_name_pre: document.getElementById("room_name_pre").value,
  };

  if (!payload.subject_code_pre) {
    showNotification("กรุณาเลือกรหัสวิชา", "warning");
    return;
  }

  fetch("/api/pre/add/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCookie("csrftoken"),
    },
    body: JSON.stringify(payload),
  })
    .then((r) => r.json())
    .then((d) => {
      if (d.status === "success") {
        flashToast("เพิ่มวิชาล่วงหน้าสำเร็จ", "success", "เพิ่มสำเร็จ");
        location.reload();
      } else {
        showNotification(
          "เกิดข้อผิดพลาด: " + (d.message || "ไม่สามารถเพิ่มข้อมูลได้"),
          "error"
        );
      }
    })
    .catch(() => showNotification("เกิดข้อผิดพลาดในการเพิ่มข้อมูล", "error"));
}

function confirmDelete(button){
  const row  = button.closest("tr");
  const id   = row.getAttribute("data-id");
  const name = row.querySelector("td")?.innerText?.trim() || "วิชาล่วงหน้า";

  if (bsDel && btnConfirmDel) {
    pendingDeleteId = id;
    if (delNameEl) delNameEl.textContent = name;
    bsDel.show();

    const handler = async () => {
      try {
        btnConfirmDel.disabled = true;
        const r = await fetch(`/api/pre/delete/${pendingDeleteId}/`, {
          method: "DELETE",
          headers: { "X-CSRFToken": getCookie("csrftoken"), "Accept": "application/json" },
        });
        const d = await r.json();
        if (d.status === "success") {
          showNotification("ลบข้อมูลเรียบร้อยแล้ว", "success", "ลบสำเร็จ");
          bsDel.hide();
          row.remove();
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
    btnConfirmDel.addEventListener("click", handler, { once: true });
  } else {
    // fallback ถ้าไม่มี modal
    if (!confirm("ต้องการลบรายการนี้ใช่ไหม?")) return;
    fetch(`/api/pre/delete/${id}/`, {
      method: "DELETE",
      headers: { "X-CSRFToken": getCookie("csrftoken") },
    })
      .then(r => r.json())
      .then(d => {
        if (d.status === "success") {
          row.remove();
          showNotification("ลบข้อมูลเรียบร้อยแล้ว", "success", "ลบสำเร็จ");
        } else {
          showNotification("เกิดข้อผิดพลาดในการลบข้อมูล", "error", "ลบไม่สำเร็จ");
        }
      })
      .catch(() => showNotification("เกิดข้อผิดพลาดในการลบข้อมูล", "error", "ลบไม่สำเร็จ"));
  }
}

let editRow = null;
let editId = null;

async function openEditModal(button) {
  editRow = button.closest("tr");
  editId  = editRow.getAttribute("data-id");
  const cells = editRow.getElementsByTagName("td");

  setSelectValue(document.getElementById("editteacher_name_pre"), cells[0].innerText.trim());
  setSelectValue(document.getElementById("editsubject_code_pre"),  cells[1].innerText.trim());
  setSelectValue(document.getElementById("editsubject_name_pre"),  cells[2].innerText.trim());
  setSelectValue(document.getElementById("editsubject_type_pre"),  cells[3].innerText.trim());
  setSelectValue(document.getElementById("edittype_pre"),         cells[4].innerText.trim());
  setSelectValue(document.getElementById("editstudent_group_pre"), cells[5].innerText.trim());

  document.getElementById("edithours_pre").value = cells[6].innerText.trim();

  // ✅ แก้ id ให้ตรงกับ HTML: edit_pre_section_num
  const secText = (cells[7].querySelector('.badge')?.innerText || cells[7].innerText).trim();
  document.getElementById("edit_pre_section_num").value = parseSectionToNum(secText);

  setSelectValue(document.getElementById("editday_pre"), cells[8].innerText.trim());
  await loadStartTimesForEdit();
  setSelectValue(document.getElementById("editstart_time_pre"), cells[9].innerText.trim());

  await loadStopTimesForEdit();
  setSelectValue(document.getElementById("editstop_time_pre"), cells[10].innerText.trim());

  setSelectValue(document.getElementById("editroom_name_pre"), cells[11].innerText.trim());

  new bootstrap.Modal(document.getElementById("editModal")).show();
}

function saveEdit() {
  // ✅ อ่านเลขจากช่องใหม่ แล้วประกอบเป็น "secX"
  const sectionNum  = (document.getElementById('edit_pre_section_num').value || '').trim();
  const section_pre = composeSectionFromNum(sectionNum);

  if (!section_pre) {
    showNotification('กรุณากรอกกลุ่มเรียน (ตัวเลขหลัง sec)', 'warning');
    return;
  }

  const payload = {
    teacher_name_pre: document.getElementById("editteacher_name_pre").value,
    subject_code_pre: document.getElementById("editsubject_code_pre").value,
    subject_name_pre: document.getElementById("editsubject_name_pre").value,
    room_type_pre: document.getElementById("editsubject_type_pre").value,
    type_pre: document.getElementById("edittype_pre").value,
    student_group_name_pre: document.getElementById("editstudent_group_pre").value,
    hours_pre: Number(document.getElementById("edithours_pre").value || 0),
    // ❌ เดิม: section_pre: document.getElementById("editsection_pre").value,
    // ✅ ใหม่:
    section_pre,
    day_pre: document.getElementById("editday_pre").value,
    start_time_pre: document.getElementById("editstart_time_pre").value,
    stop_time_pre: document.getElementById("editstop_time_pre").value,
    room_name_pre: document.getElementById("editroom_name_pre").value,
  };

  fetch(`/api/pre/update/${editId}/`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCookie("csrftoken"),
    },
    body: JSON.stringify(payload),
  })
    .then((r) => r.json())
    .then((d) => {
      if (d.status === "success") {
        flashToast("แก้ไขข้อมูลเรียบร้อยแล้ว", "success", "แก้ไขสำเร็จ");
        bootstrap.Modal.getInstance(document.getElementById("editModal")).hide();
        location.reload();
      } else {
        showNotification("เกิดข้อผิดพลาดในการแก้ไขข้อมูล", "error");
      }
    })
    .catch(() => showNotification("เกิดข้อผิดพลาดในการแก้ไขข้อมูล", "error"));
}

function deleteAllPre(){
  if (bsDelAll && btnConfirmAll) {
    bsDelAll.show();

    const handler = async () => {
      try {
        btnConfirmAll.disabled = true;
        const r = await fetch('/api/pre/delete-all/', {
          method: 'DELETE',
          headers: { 'X-CSRFToken': getCookie('csrftoken'), 'Accept': 'application/json' }
        });
        const d = await r.json();
        if (d.status === 'success') {
          showNotification('ลบวิชาล่วงหน้าทั้งหมดเรียบร้อยแล้ว', 'success', 'ลบทั้งหมดสำเร็จ');
          bsDelAll.hide();
          location.reload();
        } else {
          showNotification('เกิดข้อผิดพลาดในการลบทั้งหมด', 'error', 'ลบไม่สำเร็จ');
        }
      } catch {
        showNotification('เกิดข้อผิดพลาดในการลบทั้งหมด', 'error', 'ลบไม่สำเร็จ');
      } finally {
        btnConfirmAll.disabled = false;
        btnConfirmAll.removeEventListener('click', handler);
      }
    };
    btnConfirmAll.addEventListener('click', handler, { once:true });
  } else {
    // fallback ถ้าไม่มี modal
    if(!confirm("ต้องการลบข้อมูลทั้งหมดใช่ไหม?")) return;
    fetch('/api/pre/delete-all/', {
      method:'DELETE',
      headers:{ 'X-CSRFToken': getCookie('csrftoken') }
    })
    .then(r=>r.json())
    .then(d=>{
      if(d.status==='success'){
        showNotification('ลบวิชาล่วงหน้าทั้งหมดเรียบร้อยแล้ว','success','ลบทั้งหมดสำเร็จ');
        location.reload();
      }else{
        showNotification('เกิดข้อผิดพลาดในการลบทั้งหมด','error','ลบไม่สำเร็จ');
      }
    })
    .catch(()=> showNotification('เกิดข้อผิดพลาดในการลบทั้งหมด','error','ลบไม่สำเร็จ'));
  }
}

// ===== init wiring =====
document.addEventListener("DOMContentLoaded", async () => {
  await populateSelect("/api/teachers/", "teacher_name_pre", (t) => ({
    value: t.name,
    label: t.name,
  }));
  await populateSelect("/api/subjects/", "subject_code_pre", (s) => ({
    value: s.code,
    label: s.code,
    dataset: { sid: s.id },
  }));
  await populateSelect("/api/subjects/", "subject_name_pre", (s) => ({
    value: s.name,
    label: s.name,
    dataset: { sid: s.id },
  }));
  wireSubjectCodeNameSync("subject_code_pre", "subject_name_pre");

  await populateSelect("/api/room/list/", "room_name_pre", (r) => ({
    value: r.name,
    label: `${r.name}   ${r.type_name}`,
    dataset: { typeName: r.type_name },
  }));
  document.getElementById("type_pre")?.addEventListener("change", () => {
    const wanted = document.getElementById("type_pre").value.trim();
    filterRoomOptions("room_name_pre", wanted);
  });

  await populateSelect("/api/roomtype/list/", "type_pre", (rt) => ({
    value: rt.name,
    label: rt.name,
  }));
  await populateSelect(
    "/api/studentgroup/list/",
    "student_group_pre",
    (sg) => ({ value: sg.name, label: sg.name })
  );

  await populateSelect("/api/meta/days/", "day_pre", (d) => ({
    value: d.value,
    label: d.text,
  }));
  await loadStartTimesForCreate();
  document
    .getElementById("day_pre")
    ?.addEventListener("change", loadStartTimesForCreate);
  document
    .getElementById("start_time_pre")
    ?.addEventListener("change", loadStopTimesForCreate);

  // ------ Modal dropdowns ------
  await populateSelect("/api/teachers/", "editteacher_name_pre", (t) => ({
    value: t.name,
    label: t.name,
  }));
  await populateSelect("/api/subjects/", "editsubject_code_pre", (s) => ({
    value: s.code,
    label: s.code,
    dataset: { sid: s.id },
  }));
  await populateSelect("/api/subjects/", "editsubject_name_pre", (s) => ({
    value: s.name,
    label: s.name,
    dataset: { sid: s.id },
  }));
  wireSubjectCodeNameSync("editsubject_code_pre", "editsubject_name_pre");

  await populateSelect("/api/room/list/", "editroom_name_pre", (r) => ({
    value: r.name,
    label: `${r.name}   ${r.type_name}`,
    dataset: { typeName: r.type_name },
  }));
  document.getElementById("edittype_pre")?.addEventListener("change", () => {
    const wanted = document.getElementById("edittype_pre").value.trim();
    filterRoomOptions("editroom_name_pre", wanted);
  });

  await populateSelect("/api/roomtype/list/", "edittype_pre", (rt) => ({
    value: rt.name,
    label: rt.name,
  }));
  await populateSelect(
    "/api/studentgroup/list/",
    "editstudent_group_pre",
    (sg) => ({ value: sg.name, label: sg.name })
  );

  await populateSelect("/api/meta/days/", "editday_pre", (d) => ({
    value: d.value,
    label: d.text,
  }));
  await loadStartTimesForEdit();
  document
    .getElementById("editday_pre")
    ?.addEventListener("change", loadStartTimesForEdit);
  document
    .getElementById("editstart_time_pre")
    ?.addEventListener("change", loadStopTimesForEdit);
});

// ===== helper loaders for meta times =====
async function loadStartTimesForCreate() {
  const day = document.getElementById("day_pre")?.value || "";
  if (!day) {
    document.getElementById("start_time_pre").innerHTML =
      '<option value="">เลือกเวลาเริ่ม</option>';
    return;
  }
  await populateSelect(
    `/api/meta/start-times/?day=${day}`,
    "start_time_pre",
    (t) => ({
      value: t.value || t.start_time || t,
      label: t.text || t.start_time || t,
    })
  );
  await loadStopTimesForCreate();
}

async function loadStopTimesForCreate() {
  const day = document.getElementById("day_pre")?.value || "";
  const start = document.getElementById("start_time_pre")?.value || "";
  const stopSel = document.getElementById("stop_time_pre");
  if (!day || !start) {
    stopSel.innerHTML = '<option value="">คำนวณอัตโนมัติ</option>';
    return;
  }
  await populateSelect(
    `/api/meta/stop-times/?day=${day}&start=${start}`,
    "stop_time_pre",
    (t) => ({
      value: t.value || t.stop_time || t,
      label: t.text || t.stop_time || t,
    })
  );
  const hours = document.getElementById("hours_pre").value;
  const end = calcEnd(start, hours);
  if (end) {
    let hit = [...stopSel.options].find(
      (o) => o.value === end || o.text === end
    );
    if (!hit) {
      const opt = document.createElement("option");
      opt.value = end;
      opt.text = end;
      stopSel.appendChild(opt);
      hit = opt;
    }
    stopSel.value = end;
  }
}

async function loadStartTimesForEdit() {
  const day = document.getElementById("editday_pre")?.value || "";
  if (!day) {
    document.getElementById("editstart_time_pre").innerHTML =
      '<option value="">เลือกเวลาเริ่ม</option>';
    return;
  }
  await populateSelect(
    `/api/meta/start-times/?day=${day}`,
    "editstart_time_pre",
    (t) => ({
      value: t.value || t.start_time || t,
      label: t.text || t.start_time || t,
    })
  );
  await loadStopTimesForEdit();
}
async function loadStopTimesForEdit() {
  const day = document.getElementById("editday_pre")?.value || "";
  const start = document.getElementById("editstart_time_pre")?.value || "";
  const stopSel = document.getElementById("editstop_time_pre");
  if (!day || !start) {
    stopSel.innerHTML = '<option value="">เลือกเวลาสิ้นสุด</option>';
    return;
  }
  await populateSelect(
    `/api/meta/stop-times/?day=${day}&start=${start}`,
    "editstop_time_pre",
    (t) => ({
      value: t.value || t.stop_time || t,
      label: t.text || t.stop_time || t,
    })
  );
  const hours = document.getElementById("edithours_pre").value;
  const end = calcEnd(start, hours);
  if (end) {
    let hit = [...stopSel.options].find(
      (o) => o.value === end || o.text === end
    );
    if (!hit) {
      const opt = document.createElement("option");
      opt.value = end;
      opt.text = end;
      stopSel.appendChild(opt);
      hit = opt;
    }
    stopSel.value = end;
  }
}
