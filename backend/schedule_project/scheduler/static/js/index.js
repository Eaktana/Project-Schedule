"use strict";

/* ===== Utilities ===== */
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

/* ===== Modal state helper (ต้องมี) ===== */
function setModalState(state, opts = {}) {
  const processing = document.getElementById("stateProcessing");
  const success    = document.getElementById("stateSuccess");
  const error      = document.getElementById("stateError");
  const footer     = document.getElementById("processingFooter");

  [processing, success, error].forEach(el => el.classList.add("d-none"));
  footer.innerHTML = "";

  if (state === "processing") {
    const msgEl = document.getElementById("processingMessage");
    if (msgEl && opts.message) msgEl.textContent = opts.message; // << ตรงนี้ของคุณมีแล้ว
    processing.classList.remove("d-none");
  }
  if (state === "success") {
    success.classList.remove("d-none");
    footer.innerHTML = `<button type="button" class="btn btn-primary" id="btnView">ดูตาราง</button>`;

    // โหลดล่วงหน้า 1 ครั้งทันทีหลังประมวลผลเสร็จ
    loadGeneratedTable().catch(()=>{});

    document.getElementById("btnView").onclick = () => {
      bootstrap.Modal.getInstance(document.getElementById("processingModal"))?.hide();
      const genListEl = document.getElementById("generatedListModal");
      new bootstrap.Modal(genListEl, { backdrop: true }).show();
    };
  }
}

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

/* wrapper ให้เรียกสั้นแบบเดียวกับหน้าอื่น */
function showNotification(message, type = "info", title = null){
  const map = { success:"success", warning:"warning", error:"danger", info:"info", debug:"info" };
  const defaults = { success:"สำเร็จ", warning:"คำเตือน", danger:"ผิดพลาด", info:"แจ้งเตือน" };
  const kind = map[type] || "info";
  showToast(kind, title ?? defaults[kind] ?? "แจ้งเตือน", message);
}

// ===== GeneratedSchedule Delete Handlers =====
let __genDelId = null;

function collectGeneratedIds() {
  return [...document.querySelectorAll('#generatedTable tbody tr[data-id]')]
    .map(tr => tr.dataset.id).filter(Boolean);
}

window.handleDeleteGenerated = (btn) => {
  const tr = btn.closest('tr');
  __genDelId = tr?.dataset.id || null;
  const code = tr?.querySelector('td:nth-child(2)')?.innerText?.trim() || '';
  const name = tr?.querySelector('td:nth-child(3)')?.innerText?.trim() || '';
  document.getElementById('del_gen_name').textContent = `${code} ${name}`.trim() || '-';
  new bootstrap.Modal(document.getElementById('confirmDeleteGeneratedModal')).show();
};

document.getElementById('btnConfirmDeleteGenerated')?.addEventListener('click', async () => {
  if (!__genDelId) return;
  try {
    const r = await fetch('/api/schedule/delete-selected/', {
      method: 'POST',
      headers: { 'Content-Type':'application/json', 'X-CSRFToken': getCookie('csrftoken') },
      body: JSON.stringify({ schedule_ids: [Number(__genDelId)] })
    });
    if (r.ok) {
      showToast('success','ลบแล้ว','ลบรายการสำเร็จ');
      document.querySelector(`#generatedTable tr[data-id="${__genDelId}"]`)?.remove();
      __genDelId = null;
      bootstrap.Modal.getInstance(document.getElementById('confirmDeleteGeneratedModal'))?.hide();
    } else {
      showToast('danger','ลบไม่สำเร็จ', `HTTP ${r.status}`);
    }
  } catch (e) {
    showToast('danger','ลบไม่สำเร็จ', e.message || 'เกิดข้อผิดพลาด');
  }
});

document.getElementById('btnConfirmDeleteAllGenerated')?.addEventListener('click', async () => {
  const ids = collectGeneratedIds();
  if (!ids.length) { showToast('info','ไม่พบรายการ','ไม่มีรายการให้ลบ'); return; }
  try {
    const r = await fetch('/api/schedule/delete-selected/', {
      method: 'POST',
      headers: { 'Content-Type':'application/json', 'X-CSRFToken': getCookie('csrftoken') },
      body: JSON.stringify({ schedule_ids: ids.map(Number) })
    });
    if (r.ok) {
      showToast('success','ลบแล้ว','ลบตารางที่สร้างแล้วทั้งหมดสำเร็จ');
      document.querySelectorAll('#generatedTable tbody tr[data-id]').forEach(tr => tr.remove());
      bootstrap.Modal.getInstance(document.getElementById('confirmDeleteAllGeneratedModal'))?.hide();
    } else {
      showToast('danger','ลบทั้งหมดไม่สำเร็จ', `HTTP ${r.status}`);
    }
  } catch (e) {
    showToast('danger','ลบทั้งหมดไม่สำเร็จ', e.message || 'เกิดข้อผิดพลาด');
  }
});

async function loadGeneratedTable() {
  const tbody = document.querySelector('#generatedTable tbody');
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="12" class="text-center text-muted py-3">กำลังโหลด...</td></tr>`;

  try {
    const res = await fetch('/api/schedule/generated/');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const rows = data.results || [];

    const esc = (s) => String(s ?? "")
      .replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;")
      .replaceAll('"',"&quot;").replaceAll("'","&#039;");

    const dayBadge = (d) => {
      const m = {
        "จันทร์": 'style="background:#ffea70;color:#111;"',
        "อังคาร": 'style="background:#fd96b9;color:#111;"',
        "พุธ": 'style="background:#9dff9d;color:#111;"',
        "พฤหัสบดี": 'style="background:#ffc56f;color:#111;"',
        "ศุกร์": 'style="background:#a7f2ff;color:#111;"',
        "เสาร์": 'style="background:#b799fd;color:#111;"',
        "อาทิตย์": 'style="background:#ff6d6d;color:#111;"',
      };
      const attr = m[d] || 'style="background:#f1f3f5;color:#212529;"';
      return `<span class="badge" ${attr}>${d || "—"}</span>`;
    };

    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="12" class="text-center text-muted">ไม่มีข้อมูล</td></tr>`;
      return;
    }

    tbody.innerHTML = rows.map(g => `
      <tr data-id="${g.id}">
        <td><span class="badge" style="background:#00000020;color:#111;">${esc(g.teacher)}</span></td>
        <td><span class="badge bg-primary">${esc(g.subject_code)}</span></td>
        <td><span class="badge" style="background:#65baff65;color:#111;">${esc(g.subject_name)}</td>
        <td><span class="badge" style="background:#00000020;color:#111;">${esc(g.type || "-")}</span></td>
        <td><span class="badge" style="background:#00000020;color:#111;">${esc(g.student_group || "-")}</span></td>
        <td><span class="badge" style="background:#00000020;color:#111;">${esc(g.hours ?? "-")}</span></td>
        <td><span class="badge" style="background:#00000020;color:#111;">${esc(g.section || "-")}</span></td>
        <td>${dayBadge(g.day_of_week || "—")}</td>
        <td><span class="badge" style="background:#00000020;color:#111;">${esc(g.start_time || "")}</span></td>
        <td><span class="badge" style="background:#00000020;color:#111;">${esc(g.stop_time || "")}</span></td>
        <td><span class="badge" style="background:#00000020;color:#111;">${esc(g.room || "-")}</span></td>
        <td class="text-nowrap">
          <div class="d-inline-flex gap-2 align-items-center">
            <button class="btn btn-danger-gradient btn-sm d-inline-flex align-items-center"
                    onclick="handleDeleteGenerated(this)" title="ลบ">
              <i class="bi bi-trash me-1"></i>
            </button>
          </div>
        </td>
      </tr>
    `).join('');
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="12" class="text-center text-danger">โหลดข้อมูลไม่สำเร็จ</td></tr>`;
  }
}

let __genRunning = false;
let genCtrl = null;

function generateSchedule() {
  if (__genRunning) {
    showToast("warning","กำลังประมวลผล","ระบบกำลังสร้างตารางอยู่");
    return;
  }
  __genRunning = true;

  const modalEl = document.getElementById("processingModal");
  const modal = new bootstrap.Modal(modalEl, { backdrop:"static", keyboard:false });
  setModalState("processing", { message: "กำลังประมวลผล" }); // ← ตั้งข้อความได้ (ดูข้อ B)
  modal.show();

  genCtrl = new AbortController();

  fetch("/api/schedule/generate/", {
    method: "POST",
    headers: { "Content-Type":"application/json", "X-CSRFToken": getCookie("csrftoken") },
    signal: genCtrl.signal
  })
  .then(async (r) => {
    if (r.status === 204) { setModalState("error", { message: "ยกเลิกแล้ว" }); return; }
    const d = await r.json().catch(()=> ({}));

    if (r.status === 409) { setModalState("error", { message: d?.message || "ระบบกำลังทำงานอยู่" }); return; }
    if (r.ok && (d.status === "success" || !d.status)) setModalState("success");
    else setModalState("error", { message: d?.message || "เกิดข้อผิดพลาด" });
  })
  .catch((e) => {
    if (e.name !== "AbortError") setModalState("error", { message: "เกิดข้อผิดพลาดในการสร้าง" });
  })
  .finally(() => { __genRunning = false; genCtrl = null; });
}


async function doCancelGeneration() {
  try { genCtrl?.abort(); } catch {}
  try {
    await fetch("/api/schedule/cancel/", {
      method: "POST",
      headers: { "X-CSRFToken": getCookie("csrftoken") }
    });
  } catch {}
  setModalState("error", { message: "ยกเลิกการสร้างตารางสอนแล้ว" });
}

// === bind ปุ่ม X และตอนปิดโมดัล ให้ยกเลิกฝั่งเซิร์ฟเวอร์ด้วย ===
(function bindCancel(){
  const modalEl = document.getElementById("processingModal");
  const btnX    = document.getElementById("btnCancelGeneration");
  btnX?.addEventListener("click", doCancelGeneration);
  modalEl?.addEventListener("hide.bs.modal", doCancelGeneration);
})();

const __listCache = new Map(); 

// โหลดรายการจาก GeneratedSchedule
async function loadScheduleSelect() {
  const grid = document.getElementById('tt-items-grid');
  const spin = document.getElementById('tt-select-spinner');
  const empty = document.getElementById('tt-select-empty');
  const categoryEl = document.getElementById('ttCategory');
  const selectedCategory = (categoryEl?.value || 'Teacher');
  const q = (document.getElementById('ttSearch')?.value || '').trim();
  const cacheKey = `${selectedCategory.toLowerCase()}|${q}`;

  spin?.classList.remove('d-none');
  empty?.classList.add('d-none');
  grid.innerHTML = '';

  try {
    // ใช้แคชถ้ามี
    let data;
    if (__listCache.has(cacheKey)) {
      data = __listCache.get(cacheKey);
    } else {
      const res = await fetch(`/api/schedule/list/?view=${selectedCategory.toLowerCase()}&q=${encodeURIComponent(q)}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      data = await res.json();
      __listCache.set(cacheKey, data);
    }

    const items = (data.results || []).map(x => x.display).filter(Boolean);
    grid.innerHTML = items.map(nameRaw => {
      const nameEsc = esc(String(nameRaw ?? ''));
      const icon = (selectedCategory === "Teacher")
        ? '<i class="bi bi-person-circle fs-4"></i>'
        : (selectedCategory === "Room")
          ? '<i class="bi bi-geo-alt fs-4"></i>'
          : '<i class="bi bi-book fs-4"></i>';
      return `
        <div class="sb-card tt-item-card" data-key="${nameRaw}" role="button" tabindex="0">
          <div class="sb-head">
            <div class="sb-icon">${icon}</div>
            <div class="sb-title" title="${nameEsc}">${nameEsc}</div>
          </div>
          <div class="sb-sub">คลิกเพื่อดูตารางสอน</div>
        </div>
      `;
    }).join('');

    grid.classList.add('sb-grid');
    grid.style.display = 'grid';
    wireItemClicks();

    spin?.classList.add('d-none');
    empty?.classList.toggle('d-none', items.length !== 0);
    scheduleListLoaded = true; // ✅ ทำเครื่องหมายว่าโหลดแล้ว
  } catch (err) {
    console.error(err);
    spin?.classList.add('d-none');
    empty?.classList.remove('d-none');
    empty.textContent = 'โหลดข้อมูลไม่สำเร็จ';
  }
}
// โหลดเมื่อโมดัลกำลังเปิด (ครั้งแรกเท่านั้น)
let scheduleListLoaded = false;
let ttSearchTimer = null;

document.getElementById('ttSearch')?.addEventListener('input', () => {
  clearTimeout(ttSearchTimer);
  ttSearchTimer = setTimeout(() => {
    scheduleListLoaded = false;
    loadScheduleSelect();
  }, 300);
});

// หากมีการเปลี่ยน dropdown "เลือกประเภท" หรือช่องค้นหา แล้วอยากรีโหลดด้วย:
document.getElementById('ttCategory')?.addEventListener('change', () => {
  scheduleListLoaded = false;
  __listCache.clear(); // เคลียร์แคชเมื่อเปลี่ยนหมวด
  loadScheduleSelect();
});

// โหลดรายการทุกครั้งที่เปิดโมดัล "ตารางสอน"
document.getElementById('ttScheduleModal')?.addEventListener('shown.bs.modal', () => {
  if (!scheduleListLoaded) loadScheduleSelect(); // ✅ ไม่โหลดซ้ำถ้าเพิ่งโหลดแล้ว
  requestAnimationFrame(resizeTimetableRows);
  setTimeout(resizeTimetableRows, 0);
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(() => setTimeout(resizeTimetableRows, 0));
  }
});

// ====== helper ======
const esc = (s) => String(s ?? "")
  .replaceAll("&","&amp;")
  .replaceAll("<","&lt;")
  .replaceAll(">","&gt;")
  .replaceAll('"',"&quot;")
  .replaceAll("'","&#039;");

// ===== Calendar constants =====
const TT_DAY_ORDER = ["จันทร์","อังคาร","พุธ","พฤหัสบดี","ศุกร์","เสาร์","อาทิตย์"];

// ช่วงเวลาที่อยากโชว์บนหัวตาราง (ตัวอย่างภาพ: 08:00 ถึง 20:30 ⇒ 25 คาบ)
const TT_START = { h: 8,  m: 0  };   // เริ่ม 08:00
const TT_END   = { h: 21, m: 0 };   // จบที่ 21:00 → ได้ 26 คาบ 30 นาที
const TT_SLOT_MIN = 30;              // ความละเอียดคาบ (นาที)

// state ของตาราง
let ttRowsRaw = [];
let ttRowsFiltered = [];

// สลับไปมุมมอง "ตาราง"
function showTableView() {
  document.getElementById('tt-select-view')?.classList.add('d-none');
  document.getElementById('tt-table-view')?.classList.remove('d-none');
  document.getElementById('tt-controls')?.classList.add('d-none');
  document.getElementById('tt-toolbar')?.classList.remove('d-none');
  requestAnimationFrame(resizeTimetableRows);
}

function showSelectView() {

  document.getElementById('tt-table-view')?.classList.add('d-none');
  document.getElementById('tt-select-view')?.classList.remove('d-none');
  document.getElementById('tt-controls')?.classList.remove('d-none');
  document.getElementById('tt-toolbar')?.classList.add('d-none');

  const s = document.getElementById('ttSearchWithin'); 
  if (s) s.value = "";
}

// โหลดแถวตารางสำหรับรายการที่เลือก แล้วเติมลงตาราง
async function loadTableFor(view, key) {
  const tbl = document.getElementById('tt-calendar');
  const empty = document.getElementById('tt-calendar-empty');
  if (tbl) tbl.innerHTML = `<thead><tr><th class="text-center py-4">กำลังโหลด...</th></tr></thead>`;
  empty?.classList.add('d-none');

  try {
    const res = await fetch(`/api/schedule/timetable/?view=${encodeURIComponent(view)}&key=${encodeURIComponent(key)}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    const rows = (data.items || []).map(r => ({
      Day: r.Day || "",
      StartTime: r.StartTime || "",
      StopTime: r.StopTime || "",
      Subject_Name: r.Subject_Name || "",
      Course_Code: r.Course_Code || "",
      Teacher: r.Teacher || "",
      Room: r.Room || "",
      Type: (r.Type || "").toLowerCase(),
      Student_Group: r.Student_Group || "",
      Section: r.Section || ""
    }));

    ttRowsRaw = rows;
    showTableView();
    applyTimetableFilter();   // กรอง/เรนเดอร์ครั้งแรก (รองรับกรณีมีค่าค้างในช่องค้นหา)
  } catch (err) {
    console.error(err);
    if (tbl) tbl.innerHTML = "";
    empty?.classList.remove('d-none');
    empty.textContent = 'โหลดตารางไม่สำเร็จ';
  }
}

// จับคลิกทุกการ์ดหลังจากโหลดรายชื่อเสร็จ
function wireItemClicks() {
  document.querySelectorAll('.tt-item-card').forEach(el => {

    if (el.__openHandler) el.removeEventListener('click', el.__openHandler);

    el.__openHandler = async (ev) => {
      if (selectMode) return;        // <-- กันเปิดตารางระหว่างโหมดเลือก
      const key  = el.dataset.key || '';
      const view = (document.getElementById('ttCategory')?.value || 'Teacher').toLowerCase();
      await loadTableFor(view, key);
    };
    el.addEventListener('click', el.__openHandler);
  });
}

function applyTimetableFilter() {
  const q = (document.getElementById('ttSearchWithin')?.value || "").trim().toLowerCase();
  if (!q) ttRowsFiltered = ttRowsRaw.slice();
  else {
    ttRowsFiltered = ttRowsRaw.filter(r =>
      [r.Subject_Name, r.Course_Code, r.Teacher, r.Room, r.Type, r.Student_Group]
      .some(v => String(v||"").toLowerCase().includes(q))
    );
  }
  renderCalendar(ttRowsFiltered);
}

// ผูกอีเวนต์ของทูลบาร์ (รันครั้งเดียว)
(function wireToolbar(){
  document.getElementById('ttSearchWithin')?.addEventListener('input', () => {
    clearTimeout(window.__ttFilterTimer);
    window.__ttFilterTimer = setTimeout(applyTimetableFilter, 200);
  });
  document.getElementById('ttReset')?.addEventListener('click', () => {
    const s = document.getElementById('ttSearchWithin'); if (s) s.value = "";
    applyTimetableFilter();
  });
  // ปุ่มกลับ 2 จุด (ใน header เดิม และใน toolbar)
  document.getElementById('ttBackBtn2')?.addEventListener('click', showSelectView);
  document.getElementById('ttBackBtn')?.addEventListener('click', showSelectView);
})();

function renderCalendar(rows) {
  const tbl = document.getElementById('tt-calendar');
  const empty = document.getElementById('tt-calendar-empty');
  if (!tbl) return;

  // จำนวนคอลัมน์ = จำนวนคาบครึ่งชั่วโมง
  const SLOTS = __SLOTS;
  tbl.style.setProperty('--tt-hours', String(SLOTS));

  const blocksByDay = groupToBlocks(rows);
  const any = Object.values(blocksByDay).some(arr => arr.length);
  empty?.classList.toggle('d-none', any);
  if (!any) { tbl.innerHTML = ""; return; }

  // colgroup: 1 คอลัมน์วัน + SLOTS คอลัมน์เวลา
  let colgroup = '<colgroup><col class="tt-day-col">';
  for (let i = 0; i < SLOTS; i++) colgroup += '<col class="tt-hour-col">';
  colgroup += '</colgroup>';

  // thead: แสดง “08.00-08.30 …”
  let thead = '<thead><tr><th class="sticky-top bg-light">วัน / เวลา</th>';
  for (let i = 0; i < SLOTS; i++) thead += `<th class="text-center sticky-top bg-light">${slotLabel(i)}</th>`;
  thead += '</tr></thead>';

  // tbody: วาง td โดยคิด colspan เป็นจำนวนคาบ
  let tbody = "<tbody>";
  for (const day of TT_DAY_ORDER) {
    const blocks = blocksByDay[day] || [];
    const startIndex = Object.fromEntries(blocks.map(b => [String(b.sh), b]));
    tbody += `<tr><th class="bg-light">${day}</th>`;
    for (let s = 0; s < SLOTS; s++) {
      const b = startIndex[String(s)];
      if (b) {
        const span = Math.max(1, b.eh - b.sh);
        tbody += `<td colspan="${span}">${slotCard(b)}</td>`;
        s += span - 1;
      } else {
        const inside = blocks.some(x => x.sh < s && x.eh > s);
        if (!inside) tbody += "<td>&nbsp;</td>";
      }
    }
    tbody += "</tr>";
  }
  tbody += "</tbody>";

  tbl.innerHTML = colgroup + thead + tbody;

  requestAnimationFrame(() => {
    syncCalendarColumnVars();
    resizeTimetableRows();
  });
}

// วัดความกว้างคอลัมน์จริง แล้ว sync เป็นตัวแปรที่ CSS ใช้
function syncCalendarColumnVars() {
  const tbl = document.getElementById('tt-calendar');
  if (!tbl) return;

  // วัดคอลัมน์ "วัน" จากแถวข้อมูลจริง (TBODY)
  const bodyRow    = tbl.tBodies?.[0]?.rows?.[0];
  const dayBodyCell= bodyRow?.cells?.[0];
  const dayHeadCell= tbl.tHead?.rows?.[0]?.cells?.[0];
  const dayW = Math.round((dayBodyCell || dayHeadCell)?.getBoundingClientRect().width || 140);

  // วัดความกว้างคอลัมน์ชั่วโมงจาก THEAD (ชั่วโมงแรก)
  const hourHeadCell = tbl.tHead?.rows?.[0]?.cells?.[1];
  const hourW = Math.round(hourHeadCell?.getBoundingClientRect().width || 120);

  // วัดความสูง THEAD เพื่อยกเส้นลงไปใต้หัวตาราง
  const theadH = Math.round(tbl.tHead?.getBoundingClientRect().height || 0);
  
  tbl.style.setProperty('--tt-daycolw', dayW + 'px');
  tbl.style.setProperty('--tt-dayw-actual', dayW + 'px');
  tbl.style.setProperty('--tt-colw',        hourW + 'px');
  tbl.style.setProperty('--tt-thead-h',     theadH + 'px');
}

// รวมคาบที่ติดกัน (ต่อเนื่อง) ภายในวันเดียวกัน
function groupToBlocks(rows) {
  const byDay = Object.fromEntries(TT_DAY_ORDER.map(d => [d, []]));

  for (const r of rows) {
    if (!byDay.hasOwnProperty(r.Day)) continue;

    const sm = tToMin(r.StartTime);
    const em = tToMin(r.StopTime);

    if (Number.isNaN(sm) || Number.isNaN(em)) continue;
    if (em <= sm) continue;

    // clamp ให้อยู่ในช่วงที่โชว์
    const sClamped = Math.max(__START_MIN, Math.min(sm, __END_MIN));
    const eClamped = Math.max(__START_MIN, Math.min(em, __END_MIN));

    let sh = minToSlotFloor(sClamped);
    let eh = minToSlotCeil(eClamped);     // จบคาบปัดขึ้น
    sh = Math.max(0, Math.min(sh, __SLOTS));
    eh = Math.max(0, Math.min(eh, __SLOTS));
    if (eh <= sh) continue;

    byDay[r.Day].push({ sh, eh, ...r });
  }

  // รวมคาบติดกันที่เป็นวิชาเดียวกันต่อเนื่อง
  const merged = {};
  for (const d of Object.keys(byDay)) {
    const xs = byDay[d].sort((a,b)=>a.sh-b.sh);
    const out = [];
    let cur = null;
    for (const b of xs) {
      if (!cur) { cur = {...b}; continue; }
      const same =  cur.Subject_Name===b.Subject_Name &&
                    cur.Course_Code===b.Course_Code &&
                    cur.Teacher===b.Teacher &&
                    cur.Room===b.Room &&
                    (cur.Type||"") === (b.Type||"") &&
                    (cur.Section||"") === (b.Section||"");
      if (same && b.sh <= cur.eh) cur.eh = Math.max(cur.eh, b.eh);
      else { out.push(cur); cur = {...b}; }
    }
    if (cur) out.push(cur);
    merged[d] = out;
  }
  return merged;
}

// หน้าตาบัตรวิชาในคาบ
function slotCard(b) {
  const type = (b.Type||"").toLowerCase();
  const cls = type.includes("lab") ? "tt-type-lab"
           : type.includes("seminar") ? "tt-type-seminar"
           : type.includes("activity") ? "tt-type-activity"
           : "tt-type-lecture";

  const timeLabel = `${b.StartTime || ""} – ${b.StopTime || ""}`;
  const teacher   = String(b.Teacher||"").replace(/^อ\./,"") || "-";

  // ใช้ Section จริงก่อน → ถ้าไม่มีค่อยใช้ Student_Group (ไม่ต้องเติมคำว่า SEC)
  const secText =
    (b.Section && String(b.Section).trim()) ||
    ((b.Student_Group && String(b.Student_Group).toUpperCase() !== 'N/A')
      ? String(b.Student_Group).trim()
      : "");

  // บนการ์ด: โชว์ “รหัส · section · ห้อง” (ถ้าไม่มี section ก็ข้าม)
  const metaLine = [ b.Course_Code || "", secText, b.Room || "" ]
    .filter(Boolean).join(" · ");

  // tooltip: โชว์ครบเหมือนเดิม
  const tooltip = [
    b.Subject_Name || "—",
    b.Course_Code ? `(${b.Course_Code})` : "",
    `เวลา: ${timeLabel}`,
    `ห้อง: ${b.Room || "-"}`,
    `ผู้สอน: ${teacher}`,
    `ประเภท: ${b.Type || "-"}`,
    b.Student_Group ? `กลุ่ม: ${b.Student_Group}` : "",
    b.Section ? `Section: ${b.Section}` : ""
  ].filter(Boolean).join("\n");
  const tooltipHtml = esc(tooltip).replaceAll('\n','<br>');

  // **ไม่มีชื่อวิชาในการ์ดแล้ว** — เหลือแค่ meta + chip ประเภท
  return `
  <div class="tt-slot ${cls}"
       title="${tooltipHtml}"
       data-bs-toggle="tooltip"
       data-bs-placement="top"
       data-bs-html="true">
    <div class="tt-body">
      <div class="tt-meta">${esc(metaLine)}</div>
    </div>
    <span class="tt-chip">${esc(b.Type || "—")}</span>
  </div>`;
}

function tToMin(t){                 // "HH:MM" -> นาทีตั้งแต่ 00:00
  if (!t) return NaN;
  const [hh, mm='0'] = String(t).trim().split(':');
  const h = parseInt(hh,10), m = parseInt(mm,10);
  if (Number.isNaN(h) || Number.isNaN(m)) return NaN;
  return h*60 + m;
}

const __START_MIN = TT_START.h*60 + TT_START.m;
const __END_MIN   = TT_END.h*60   + TT_END.m;
const __SLOTS     = Math.round((__END_MIN - __START_MIN) / TT_SLOT_MIN); // เช่น 25

function minToSlotFloor(min){        // เริ่มคาบ: ปัดลงตามช่วง 30 นาที
  return Math.floor((min - __START_MIN)/TT_SLOT_MIN);
}
function minToSlotCeil(min){         // จบคาบ: ปัดขึ้นตามช่วง 30 นาที
  return Math.ceil((min - __START_MIN)/TT_SLOT_MIN);
}

function fmtHMdot(min){              // 480 -> "08.00"
  const h = Math.floor(min/60), m = min%60;
  return `${String(h).padStart(2,'0')}.${String(m).padStart(2,'0')}`;
}
function slotLabel(idx){             // 0 -> "08.00-08.30"
  const s = __START_MIN + idx*TT_SLOT_MIN;
  const e = s + TT_SLOT_MIN;
  return `${fmtHMdot(s)}-${fmtHMdot(e)}`;
}

document.getElementById('ttScheduleModal')?.addEventListener('hide.bs.modal', () => {
  // กลับไปหน้ารายชื่อและให้ controls โชว์เหมือนเดิมทุกครั้งที่ปิดโมดัล
  showSelectView();
  document.getElementById('tt-controls')?.classList.remove('d-none');
});

function resizeTimetableRows() {
  const modalBody = document.querySelector(
    '#ttScheduleModal .modal-body'
  );
  const toolbar = document.getElementById('tt-toolbar');
  const tbl = document.getElementById('tt-calendar');
  if (!modalBody || !tbl) return;

  const theadH = tbl.tHead
    ? tbl.tHead.getBoundingClientRect().height
    : 40;

  // พื้นที่แนวตั้งทั้งหมดของส่วนเนื้อหาโมดัล
  const bodyH = modalBody.getBoundingClientRect().height;

  // ถ้า toolbar โชว์ ให้นำความสูงไปหัก
  const toolH = (toolbar && !toolbar.classList.contains('d-none'))
    ? toolbar.getBoundingClientRect().height
    : 0;

  // เส้นขอบ/ช่องว่างเล็กน้อย
  const borderY = 8;

  // ความสูงที่ให้ตารางจริง ๆ
  const availH = bodyH - toolH;

  // คำนวณความสูงต่อแถว (7 วัน)
  let h = Math.floor((availH - theadH - borderY) / 7);

  // จำกัดช่วงเพื่อความอ่านง่าย
  h = Math.max(65, Math.min(65, h));

  tbl.style.setProperty('--tt-row-h', h + 'px');
}

// ---- รวมตัวดัก resize ให้เหลืออันเดียวทั้งไฟล์ ----
let __ttResizeBound = false;
function bindTimetableResizeOnce() {
  if (__ttResizeBound) return;
  __ttResizeBound = true;

  window.addEventListener('resize', () => {
    requestAnimationFrame(() => {
      syncCalendarColumnVars();
      resizeTimetableRows();
    });
  });
}
bindTimetableResizeOnce();

/* ===== Utilities (เพิ่ม) ===== */

// คืน key ทั้งหมดที่ "แสดงอยู่" ในกริดตอนนี้
function visibleKeys(){
  return Array.from(document.querySelectorAll('#tt-items-grid .tt-item-card'))
    .map(el => el.dataset.key || '')
    .filter(Boolean);
}

// โหมดเลือก เลือกไฟล์: toggle checkbox overlay
let selectMode = false;
function toggleSelectMode(on){
  selectMode = (on !== undefined) ? on : !selectMode;

  document.querySelectorAll('#tt-items-grid .tt-item-card').forEach(card => {
    card.classList.toggle('tt-selectable', selectMode);

    if (selectMode){
      card.style.position = 'relative';
      // ใส่ checkbox overlay ถ้ายังไม่มี
      if (!card.querySelector('.tt-check')){
        const box = document.createElement('div');
        box.className = 'tt-check form-check';
        box.style.position = 'absolute';
        box.style.top = '10px';
        box.style.right = '10px';
        box.style.zIndex = '2';
        box.innerHTML = `<input class="form-check-input" type="checkbox" aria-label="เลือก">`;
        const cb = box.querySelector('input[type="checkbox"]');

        // กัน event เด้งไป handler อื่น ๆ
        cb.addEventListener('click', (e) => {
          e.stopPropagation();
          e.stopImmediatePropagation();
          card.classList.toggle('border-primary', cb.checked);
          updateSelectBtnLabel();
        });

        card.appendChild(box);
      }

      // คลิกการ์ด = toggle checkbox (และกันเปิดตาราง)
      if (!card.__tickHandler){
        card.__tickHandler = (ev) => {
          if (!selectMode) return;
          ev.stopPropagation();
          ev.stopImmediatePropagation();
          const cb = card.querySelector('input[type="checkbox"]');
          cb.checked = !cb.checked;
          card.classList.toggle('border-primary', cb.checked);
          updateSelectBtnLabel();
        };
        card.addEventListener('click', card.__tickHandler);
      }
    } else {
      // ออกจากโหมดเลือก
      card.querySelector('.tt-check')?.remove();
      card.classList.remove('border-primary');
      if (card.__tickHandler){
        card.removeEventListener('click', card.__tickHandler);
        card.__tickHandler = null;
      }
    }
  });

  updateSelectBtnLabel();
  updateToolbarButtons();
}

function updateSelectBtnLabel() {
  const btn = document.getElementById('btnSelectDownload');
  if (!btn) return;
  if (!selectMode) {
    btn.innerHTML = '<i class="bi bi-check2-square me-1"></i> เลือกไฟล์';
  } else {
    const count = selectedKeys().length;
    btn.innerHTML = `<i class="bi bi-download me-1"></i> ดาวน์โหลดที่เลือก (${count})`;
  }
}

// คืน keys ที่ถูกติ๊กในโหมดเลือก
function selectedKeys(){
  return Array.from(document.querySelectorAll('#tt-items-grid .tt-item-card input[type="checkbox"]:checked'))
    .map(cb => cb.closest('.tt-item-card').dataset.key || '')
    .filter(Boolean);
}

// โหลดใหม่เมื่อกริดเปลี่ยน เพื่อให้ checkbox มาในรายการใหม่ด้วยเวลาเข้าสู่ selectMode
const __origLoad = loadScheduleSelect;
loadScheduleSelect = async function(){
  await __origLoad();
  if (selectMode) toggleSelectMode(true);
  updateSelectBtnLabel();
  updateToolbarButtons();
};

/* ===== Download actions ===== */

/// ใช้ view ปัจจุบันจาก dropdown: teacher | room | student_group
function getView() {
  const v = (document.getElementById('ttCategory')?.value || 'Teacher').toLowerCase();
  if (v === 'group' || v === 'student' || v === 'students') return 'student_group';
  return v; // teacher | room | student_group
}

// ดาวน์โหลด ZIP หลายไฟล์
async function downloadBatch(view, keys, filename='timetables.zip') {
  if (!keys.length) { alert('ไม่พบรายการสำหรับดาวน์โหลด'); return; }
  const res = await fetch('/api/export/pdf/batch/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
    body: JSON.stringify({ view, keys })
  });
  if (!res.ok) {
    const t = await res.text().catch(()=> '');
    alert('สร้างไฟล์ไม่สำเร็จ: ' + res.status + '\n' + t);
    return;
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// ดาวน์โหลด PDF เดี่ยว (เปิดแท็บใหม่)
function downloadSingle(view, key) {
  if (!key) { alert('ยังไม่ได้ระบุรายการ'); return; }
  const url = `/api/export/pdf/?view=${encodeURIComponent(view)}&key=${encodeURIComponent(key)}`; // ← มี / ปิดท้าย path แล้ว
  window.open(url, '_blank');
}

// ปุ่ม: “ดาวน์โหลดทั้งหมด”
document.getElementById('btnDownloadAll')?.addEventListener('click', async () => {
  if (selectMode) {                 // ตอนนี้ปุ่มทำหน้าที่ยกเลิก
    toggleSelectMode(false);
    updateToolbarButtons();
    return;
  }
  // โหมดปกติ → ดาวน์โหลดทั้งหมดที่แสดง
  const view = getView();
  const keys = visibleKeys();
  if (!keys.length) { alert('ไม่พบรายการในหน้านี้'); return; }
  await downloadBatch(view, keys, 'timetables.zip');
});

document.getElementById('btnSelectDownload')?.addEventListener('click', async () => {
  if (!selectMode) {
    lockToolbarButtonWidths(true);   // ← ล็อกก่อนสลับข้อความปุ่ม
    toggleSelectMode(true);          // เข้าโหมดติ๊กเลือก
    updateToolbarButtons();          // เปลี่ยน "ทั้งหมด" -> "ยกเลิก"
    return;
  }
  const keys = selectedKeys();
  if (!keys.length){ alert('ยังไม่ได้เลือกรายการ'); return; }
  await downloadBatch(getView(), keys, 'timetables-selected.zip');
  toggleSelectMode(false);           // กลับโหมดปกติ
  updateToolbarButtons();            // คืนปุ่ม "ทั้งหมด"
  lockToolbarButtonWidths(false);    // ← ปลดล็อกเมื่อออกโหมดเลือก
});

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && selectMode) {
    toggleSelectMode(false);
    updateToolbarButtons();
  }
});

function setBtnVariant(btn, addClasses = [], removeClasses = []) {
  removeClasses.forEach(c => btn.classList.remove(c));
  addClasses.forEach(c => btn.classList.add(c));
}

// === Helper สำหรับสลับสกินปุ่ม ===
// รายชื่อคลาสสีของปุ่มที่ต้องล้างทิ้งก่อนใส่สกินใหม่
const BTN_COLOR_CLASSES = [
  'btn-dark','btn-light','btn-primary','btn-secondary',
  'btn-success','btn-danger','btn-warning','btn-info',
  'btn-outline-dark','btn-outline-light','btn-outline-primary','btn-outline-secondary',
  'btn-outline-success','btn-outline-danger','btn-outline-warning','btn-outline-info'
];

// ให้ปุ่มเป็น "พื้นดำทึบ"
function toSolidDark(btn){
  BTN_COLOR_CLASSES.forEach(c => btn.classList.remove(c));
  btn.classList.add('btn','btn-dark');
  btn.setAttribute('aria-pressed','true');
}

// ให้ปุ่มเป็น "พื้นขาว ขอบดำ"
function toOutlineDark(btn){
  BTN_COLOR_CLASSES.forEach(c => btn.classList.remove(c));
  btn.classList.add('btn','btn-outline-dark');
  btn.setAttribute('aria-pressed','false');
}

function updateToolbarButtons() {
  const btnAll  = document.getElementById('btnDownloadAll');
  const btnPick = document.getElementById('btnSelectDownload');
  if (!btnAll || !btnPick) return;

  // อัปเดตฉลากปุ่มเลือกไฟล์
  updateSelectBtnLabel?.();

  if (selectMode) {
    // ปุ่ม "ทั้งหมด" -> ยกเลิก (เป็น outline สีเทา)
    BTN_COLOR_CLASSES.forEach(c => btnAll.classList.remove(c));
    btnAll.classList.add('btn','btn-outline-secondary');
    btnAll.innerHTML = '<i class="bi bi-x-circle me-1"></i> ยกเลิก';
    btnAll.setAttribute('aria-label','ยกเลิกการเลือกไฟล์');

    // ปุ่ม "เลือกไฟล์" -> พื้นดำ (active)
    toSolidDark(btnPick);

  } else {
    // ปุ่ม "ทั้งหมด" -> กลับเป็น outline ดำ
    BTN_COLOR_CLASSES.forEach(c => btnAll.classList.remove(c));
    btnAll.classList.add('btn','btn-outline-dark');
    btnAll.innerHTML = '<i class="bi bi-file-earmark-arrow-down me-1"></i> ทั้งหมด';
    btnAll.setAttribute('aria-label','ดาวน์โหลดทั้งหมดที่แสดง');

    // ปุ่ม "เลือกไฟล์" -> กลับเป็นพื้นขาว ขอบดำ
    toOutlineDark(btnPick);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  updateToolbarButtons();
});

// วางครั้งเดียวหลัง DOMContentLoaded
document.addEventListener('mouseover', (e) => {
  const el = e.target.closest('#tt-calendar [data-bs-toggle="tooltip"]');
  if (!el || el.dataset.tipReady) return;
  new bootstrap.Tooltip(el);
  el.dataset.tipReady = '1';
});


// กันไม่ให้ปุ่มยืด/หดเมื่อข้อความเปลี่ยน
function lockToolbarButtonWidths(lock) {
  ['btnDownloadAll', 'btnSelectDownload'].forEach(id => {
    const b = document.getElementById(id);
    if (!b) return;
    if (lock) {
      const w = Math.ceil(b.getBoundingClientRect().width);
      b.style.width = w + 'px';
      b.style.whiteSpace = 'nowrap';
    } else {
      b.style.width = '';
      b.style.whiteSpace = '';
    }
  });
}

