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

  // reset
  [processing, success, error].forEach(el => el.classList.add("d-none"));
  footer.innerHTML = "";

  if (state === "processing") {
    processing.classList.remove("d-none");
  }
  if (state === "success") {
    success.classList.remove("d-none");
    footer.innerHTML = `
      <button type="button" class="btn btn-primary" id="btnView">ดูตาราง</button>
      <button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">ปิด</button>
    `;
    document.getElementById("btnView").onclick = () => location.reload();
  }
  if (state === "error") {
    error.classList.remove("d-none");
    document.getElementById("errorMessage").textContent = opts.message || "ไม่ทราบสาเหตุ";
    footer.innerHTML = `<button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">ปิด</button>`;
  }
}

// เรียกโหลดรายการจาก GeneratedSchedule แล้วแสดงเป็นการ์ด
async function loadScheduleSelect() {
  const grid = document.getElementById('tt-items-grid');
  const spin = document.getElementById('tt-select-spinner');
  const empty = document.getElementById('tt-select-empty');
  const categoryEl = document.getElementById('ttCategory');
  const selectedCategory = (categoryEl?.value || 'Teacher');

  spin?.classList.remove('d-none');
  empty?.classList.add('d-none');
  grid.innerHTML = '';

  // ดึงคำค้นจากช่องค้นหา
  const q = (document.getElementById('ttSearch')?.value || '').trim();

  try {
    const res = await fetch(`/api/schedule/list/?view=${selectedCategory.toLowerCase()}&q=${encodeURIComponent(q)}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    const items = (data.results || []).map(x => x.display).filter(Boolean);

    grid.innerHTML = items.map((raw) => {
      const nameRaw = String(raw ?? '');
      const nameEsc = esc(nameRaw);
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
    // ค้นหาทันทีที่พิมพ์จบ ~300ms
    loadScheduleSelect();
  }, 300);
});

// หากมีการเปลี่ยน dropdown "เลือกประเภท" หรือช่องค้นหา แล้วอยากรีโหลดด้วย:
document.getElementById('ttCategory')?.addEventListener('change', () => {
  scheduleListLoaded = false;
  loadScheduleSelect();
});

// โหลดรายการทุกครั้งที่เปิดโมดัล "ตารางสอน"
document.getElementById('ttScheduleModal')?.addEventListener('shown.bs.modal', () => {
  loadScheduleSelect();
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
      Student_Group: r.Student_Group || ""
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
    el.addEventListener('click', async () => {
      const key  = el.dataset.key || '';
      const view = (document.getElementById('ttCategory')?.value || 'Teacher').toLowerCase();
      await loadTableFor(view, key);
    });
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
    document.querySelectorAll('#tt-calendar [data-bs-toggle="tooltip"]').forEach(el => {
      const t = bootstrap.Tooltip.getInstance(el);
      if (t) t.dispose();
      new bootstrap.Tooltip(el);
    });
    syncCalendarColumnVars();
    resizeTimetableRows();
    setTimeout(() => { syncCalendarColumnVars(); resizeTimetableRows(); }, 0);
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
      const same = cur.Subject_Name===b.Subject_Name &&
                   cur.Course_Code===b.Course_Code &&
                   cur.Teacher===b.Teacher &&
                   cur.Room===b.Room &&
                   (cur.Type||"") === (b.Type||"");
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

  // ใช้ Student_Group เป็น “SEC …” (ถ้าไม่ใช่ N/A), fallback ไป Section
  const secText = (b.Student_Group && String(b.Student_Group).toUpperCase() !== 'N/A')
    ? `SEC ${b.Student_Group}`
    : (b.Section ? String(b.Section).toUpperCase() : "");

  // บนการ์ด: โชว์เฉพาะ “รหัส · SEC · ห้อง”
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

/* ===== สร้างตารางสอน (เวอร์ชันเดียว) ===== */
function generateSchedule() {
  const modalEl = document.getElementById("processingModal");
  const modal = new bootstrap.Modal(modalEl, { backdrop: "static", keyboard: false });
  document.getElementById("processingMessage").textContent = "กำลังประมวลผล...";
  setModalState("processing");
  modal.show();

  fetch("/api/schedule/generate/", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRFToken": getCookie("csrftoken") },
  })
    .then(async (r) => {
      const d = await r.json().catch(() => ({}));
      // สำเร็จถ้า HTTP 200 และไม่ได้ส่ง status="error"
      if (r.ok && (!d.status || d.status === "success")) {
        setModalState("success");
      } else {
        setModalState("error", { message: d.message || "เกิดข้อผิดพลาด" });
      }
    })
    .catch((e) => {
      console.error(e);
      setModalState("error", { message: "เกิดข้อผิดพลาดในการสร้างตารางสอน" });
    });
}
