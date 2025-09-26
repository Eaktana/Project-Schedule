// /static/js/timeslot.js
document.addEventListener("DOMContentLoaded", () => {
  // ===== API endpoints =====
  const API = {
    LIST: "/api/timeslot/list/",           // GET    -> [{id?, day, start, end}]
    ADD:  "/api/timeslot/add/",            // POST   -> {day, start, end} (upsert ตาม unique (day,start,end) ได้)
    UPDATE: (id) => `/api/timeslot/update/${id}/`, // PUT    -> {day, start, end}
    DEL:  (id) => `/api/timeslot/delete/${id}/`,   // DELETE -> by id (ใช้ภายใน, UI ไม่โชว์)
    DEL_ALL: "/api/timeslot/delete-all/",  // DELETE
  };

  // ===== Elements =====
  const form = document.getElementById("timeslotForm");
  const dayInput = document.getElementById("ts_day");
  const startInput = document.getElementById("ts_start");
  const endInput = document.getElementById("ts_end");
  const tbody = document.getElementById("timeslotTableBody");
  const btnAdd = document.getElementById("btnAddTimeSlot");
  const btnDeleteAll = document.getElementById("btnDeleteAllTimeSlot");

  // edit modal
  const editEl = document.getElementById("editTimeSlotModal");
  const bsEdit = editEl ? new bootstrap.Modal(editEl) : null;
  const editId = document.getElementById("edit_timeslot_id");
  const editDay = document.getElementById("edit_ts_day");
  const editStart = document.getElementById("edit_ts_start");
  const editEnd = document.getElementById("edit_ts_end");
  const btnSave = document.getElementById("btnSaveTimeSlot");

  // delete (single) modal
  const delEl = document.getElementById("confirmDeleteTimeSlotModal");
  const bsDel = delEl ? new bootstrap.Modal(delEl) : null;
  const delDay = document.getElementById("del_ts_day");
  const delRange = document.getElementById("del_ts_range");
  const btnConfirmDel = document.getElementById("btnConfirmDeleteTimeSlot");
  let pendingDeleteId = null;

  // delete all modal
  const delAllEl = document.getElementById("confirmDeleteAllTimeSlotModal");
  const bsDelAll = delAllEl ? new bootstrap.Modal(delAllEl) : null;
  const btnConfirmDelAll = document.getElementById("btnConfirmDeleteAllTimeSlot");

  // toast
  const toastHost = document.getElementById("toastHost");

  // ===== Helpers =====
  const getCSRF = () => (document.querySelector('input[name="csrfmiddlewaretoken"]')?.value || "");
  const jsonHeaders = () => ({ "Content-Type": "application/json", "X-CSRFToken": getCSRF(), Accept: "application/json" });

  const ensureOk = async (res, fb) => {
    if (res.ok) return;
    let msg = fb;
    try { const j = await res.json(); msg = j.message || j.detail || fb; } catch {}
    throw new Error(msg || `HTTP ${res.status}`);
  };

  function showToast(kind, title, message) {
    if (!toastHost) return alert(message || title || "");
    const bg = { success:"bg-success text-white", warning:"bg-warning", danger:"bg-danger text-white", info:"bg-primary text-white" }[kind] || "bg-dark text-white";
    const el = document.createElement("div");
    el.className = "toast align-items-center border-0 shadow overflow-hidden";
    el.style.borderRadius = "12px";
    el.innerHTML = `
      <div class="toast-header ${bg}" style="border-top-left-radius:12px;border-top-right-radius:12px;">
        <strong class="me-auto">${title || ""}</strong>
        <button type="button" class="btn-close btn-close-white ms-2 mb-1" data-bs-dismiss="toast" aria-label="Close"></button>
      </div>
      <div class="toast-body">${message || ""}</div>`;
    toastHost.appendChild(el);
    new bootstrap.Toast(el, { delay: 3000, autohide: true }).show();
  }

  // sort helpers: day order Mon..Sun (ไทย)
  const dayOrder = ["จันทร์","อังคาร","พุธ","พฤหัสบดี","ศุกร์","เสาร์","อาทิตย์"];
  const dayKey = (d) => dayOrder.indexOf(d);
  const toMinutes = (hhmm) => {
    const [h,m] = (hhmm || "00:00").split(":").map(Number);
    return h*60 + m;
  };
  const sortTimeslots = (items) =>
    items.sort((a,b) => {
      const d = dayKey(a.day) - dayKey(b.day);
      if (d !== 0) return d;
      return toMinutes(a.start) - toMinutes(b.start);
    });

  // color badge for day
  const dayClass = (d) => ({
    "จันทร์":"day-chip day-mon","อังคาร":"day-chip day-tue","พุธ":"day-chip day-wed",
    "พฤหัสบดี":"day-chip day-thu","ศุกร์":"day-chip day-fri","เสาร์":"day-chip day-sat","อาทิตย์":"day-chip day-sun"
  }[d] || "day-chip");

  // ===== API wrappers =====
  const listTimeslots = async () => {
    const r = await fetch(API.LIST, { headers: { Accept: "application/json" } });
    await ensureOk(r, "โหลดข้อมูลไม่สำเร็จ");
    const j = await r.json();
    const items = j.items || j.results || j || [];
    return sortTimeslots(items);
  };

  const createTimeslot = async ({ day, start, end }) => {
    const r = await fetch(API.ADD, { method:"POST", headers: jsonHeaders(), body: JSON.stringify({ day, start, end }) });
    await ensureOk(r, "เพิ่มคาบเวลาไม่สำเร็จ");
    return r.json();
  };

  const updateTimeslot = async (id, { day, start, end }) => {
    const r = await fetch(API.UPDATE(id), { method:"PUT", headers: jsonHeaders(), body: JSON.stringify({ day, start, end }) });
    await ensureOk(r, "แก้ไขคาบเวลาไม่สำเร็จ");
    return r.json();
  };

  const deleteTimeslot = async (id) => {
    const r = await fetch(API.DEL(id), { method:"DELETE", headers: { "X-CSRFToken": getCSRF(), Accept:"application/json" }});
    await ensureOk(r, "ลบคาบเวลาไม่สำเร็จ");
    return true;
  };

  const deleteAllTimeslots = async () => {
    const r = await fetch(API.DEL_ALL, { method:"DELETE", headers: { "X-CSRFToken": getCSRF(), Accept:"application/json" }});
    await ensureOk(r, "ลบทั้งหมดไม่สำเร็จ");
    return true;
  };

  // ===== Render =====
  const rowHTML = ({ id, day, start, end }) => `
    <tr data-id="${id ?? ""}">
      <td><span class="${dayClass(day)}">${day}</span></td>
      <td class="text-center">${start}</td>
      <td class="text-center">${end}</td>
      <td class="d-flex justify-content-center gap-2">
        <button type="button" class="btn-warning-gradient btn-edit" data-id="${id ?? ""}" data-day="${day}" data-start="${start}" data-end="${end}">
          <span>แก้ไข</span>
        </button>
        <button type="button" class="btn-danger-gradient btn-delete">
          <span>ลบ</span>
        </button>
      </td>
    </tr>
  `;

  const renderTable = (items) => {
    if (!tbody) return;
    if (!Array.isArray(items) || items.length === 0) {
      tbody.innerHTML = `<tr class="empty-row"><td colspan="4" class="text-center text-muted">ไม่มีข้อมูลคาบเวลา</td></tr>`;
      return;
    }
    tbody.innerHTML = items.map(rowHTML).join("");
  };

  // ===== State & init =====
  let cache = [];
  const refresh = async () => {
    try {
      cache = await listTimeslots();
      renderTable(cache);
    } catch (e) {
      showToast("danger", "โหลดข้อมูลไม่สำเร็จ", e.message || "");
    }
  };
  refresh();

  // ===== Validation: วันเดียวกันเวลาซ้ำกันไม่ได้ + start < end =====
  const duplicateInDay = (list, day, start, end, skipId=null) =>
    list.some(x =>
      x.day === day &&
      String(x.id ?? "") !== String(skipId ?? "") &&
      x.start === start && x.end === end
    );

  const startBeforeEnd = (s,e) => toMinutes(s) < toMinutes(e);

  // ===== Events =====
  // เพิ่มคาบเวลา
  form?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const day = dayInput.value || "";
    const start = (startInput.value || "").slice(0,5);
    const end = (endInput.value || "").slice(0,5);

    if (!day || !start || !end) {
      return showToast("warning","ข้อมูลไม่ครบ","กรุณาเลือกวัน และกรอกเวลาให้ครบ");
    }
    if (!startBeforeEnd(start,end)) {
      return showToast("warning","เวลาไม่ถูกต้อง","เวลาเริ่มต้องน้อยกว่าเวลาสิ้นสุด");
    }
    if (duplicateInDay(cache, day, start, end)) {
      return showToast("warning","เวลาซ้ำ","วันเดียวกันไม่อนุญาตให้มีช่วงเวลาเดียวกันซ้ำ");
    }

    try {
      btnAdd.disabled = true;
      await createTimeslot({ day, start, end });
      form.reset();
      showToast("success","เพิ่มสำเร็จ",`${day} ${start}–${end}`);
      await refresh();
    } catch (err) {
      showToast("danger","เพิ่มไม่สำเร็จ", err.message || "");
    } finally {
      btnAdd.disabled = false;
    }
  });

  // แก้ไข/ลบ รายตัว
  tbody?.addEventListener("click", (e) => {
    const tr = e.target.closest("tr");
    if (!tr) return;
    const id = tr.dataset.id || ""; // UI ไม่แสดง id แต่ row เก็บไว้เพื่อเรียก API

    // edit
    if (e.target.closest(".btn-edit") && bsEdit) {
      const day = tr.querySelector(".day-chip")?.textContent.trim() || "";
      const start = tr.children[1]?.textContent.trim();
      const end = tr.children[2]?.textContent.trim();
      editId.value = id;
      editDay.value = day;
      editStart.value = start;
      editEnd.value = end;
      bsEdit.show();
      return;
    }

    // delete (single)
    if (e.target.closest(".btn-delete") && bsDel) {
      const day = tr.querySelector(".day-chip")?.textContent.trim() || "";
      const start = tr.children[1]?.textContent.trim();
      const end = tr.children[2]?.textContent.trim();
      pendingDeleteId = id;
      delDay.textContent = day;
      delRange.textContent = `${start}–${end}`;
      bsDel.show();
      return;
    }
  });

  // บันทึกแก้ไข
  btnSave?.addEventListener("click", async () => {
    const id = editId.value || "";
    const day = editDay.value || "";
    const start = (editStart.value || "").slice(0,5);
    const end = (editEnd.value || "").slice(0,5);

    if (!day || !start || !end) {
      return showToast("warning","ข้อมูลไม่ครบ","กรุณาเลือกวัน และกรอกเวลาให้ครบ");
    }
    if (!startBeforeEnd(start,end)) {
      return showToast("warning","เวลาไม่ถูกต้อง","เวลาเริ่มต้องน้อยกว่าเวลาสิ้นสุด");
    }
    if (duplicateInDay(cache, day, start, end, id || null)) {
      return showToast("warning","เวลาซ้ำ","วันเดียวกันไม่อนุญาตให้มีช่วงเวลาเดียวกันซ้ำ");
    }

    try {
      btnSave.disabled = true;
      if (id) {
        await updateTimeslot(id, { day, start, end });
      } else {
        // เผื่อกรณี backend ให้สร้างใหม่ถ้าไม่มี id
        await createTimeslot({ day, start, end });
      }
      bsEdit?.hide();
      showToast("success","บันทึกสำเร็จ",`${day} ${start}–${end}`);
      await refresh();
    } catch (err) {
      showToast("danger","แก้ไขไม่สำเร็จ", err.message || "");
    } finally {
      btnSave.disabled = false;
    }
  });

  // ยืนยันลบรายตัว
  btnConfirmDel?.addEventListener("click", async () => {
    if (!pendingDeleteId) return;
    try {
      btnConfirmDel.disabled = true;
      await deleteTimeslot(pendingDeleteId);
      bsDel?.hide();
      showToast("success","ลบสำเร็จ","ลบคาบเวลาแล้ว");
      pendingDeleteId = null;
      await refresh();
    } catch (err) {
      showToast("danger","ลบไม่สำเร็จ", err.message || "");
    } finally {
      btnConfirmDel.disabled = false;
    }
  });

  // ลบทั้งหมด
  btnDeleteAll?.addEventListener("click", () => bsDelAll?.show());
  btnConfirmDelAll?.addEventListener("click", async () => {
    try {
      btnConfirmDelAll.disabled = true;
      await deleteAllTimeslots();
      bsDelAll?.hide();
      showToast("success","ลบทั้งหมดสำเร็จ","ลบข้อมูลคาบเวลาทั้งหมดแล้ว");
      await refresh();
    } catch (err) {
      showToast("danger","ลบทั้งหมดไม่สำเร็จ", err.message || "");
    } finally {
      btnConfirmDelAll.disabled = false;
    }
  });
});
