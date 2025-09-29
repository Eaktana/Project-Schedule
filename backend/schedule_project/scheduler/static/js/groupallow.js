// /static/js/groupallow.js
document.addEventListener("DOMContentLoaded", () => {
  const API = {
    list:   "/api/groupallow/list/?order=-id",
    add:    "/api/groupallow/add/",
    update: (id) => `/api/groupallow/update/${id}/`,
    del:    (id) => `/api/groupallow/delete/${id}/`,
    delAll: "/api/groupallow/delete-all/",
    depts:  "/api/grouptype/list/?order=-id",
    slots:  "/api/timeslot/list/",
  };

  const DAY_ORDER = ["จันทร์","อังคาร","พุธ","พฤหัสบดี","ศุกร์","เสาร์","อาทิตย์"];
  const dayIndex = (d) => {
    const i = DAY_ORDER.indexOf(String(d || "").trim());
    return i >= 0 ? i : 99;
  };
  const toMin = (hhmm) => {
    const m = /^(\d{1,2}):(\d{2})(?::\d{2})?$/.exec(hhmm || "");
    return m ? (+m[1] * 60 + +m[2]) : 99999;
  };
  const fmt2 = (n) => String(n).padStart(2, "0");
  const parseTime = (s) => {
    const m = /(\d{1,2}):(\d{2})(?::\d{2})?/.exec(s || "");
    return m ? { h: +m[1], m: +m[2] } : null;
  };
  const addMinutes = (t, mins) => {
    const total = t.h * 60 + t.m + mins;
    const h = Math.floor((total % (24 * 60)) / 60);
    const m = total % 60;
    return `${fmt2(h)}:${fmt2(m)}`;
  };

  // Elements
  const form = document.getElementById("groupAllowForm");
  const deptSel = document.getElementById("ga_dept_id");
  const slotSel = document.getElementById("ga_slot_id");
  const tbody   = document.getElementById("groupAllowTableBody");
  const btnSubmit = document.getElementById("btnAddGroupAllow");
  const btnDeleteAll = document.getElementById("btnDeleteAllGroupAllow");
  const toastHost = document.getElementById("toastHost");

  // Modals
  const editEl = document.getElementById("editGroupAllowModal");
  const bsEdit = editEl ? new bootstrap.Modal(editEl) : null;
  const editId = document.getElementById("edit_ga_id");
  const editDept = document.getElementById("edit_ga_dept");
  const editSlot = document.getElementById("edit_ga_slot");
  const btnSave = document.getElementById("btnSaveGroupAllow");

  const delModalEl = document.getElementById("confirmDeleteModal");
  const bsDel = delModalEl ? new bootstrap.Modal(delModalEl) : null;
  const btnConfirmDelete = document.getElementById("btnConfirmDelete");
  let pendingDeleteId = null;

  const delAllModalEl = document.getElementById("confirmDeleteAllModal");
  const bsDelAll = delAllModalEl ? new bootstrap.Modal(delAllModalEl) : null;
  const btnConfirmDeleteAll = document.getElementById("btnConfirmDeleteAll");

  // Utils
  const getCSRF = () => document.querySelector('input[name="csrfmiddlewaretoken"]')?.value || "";
  const escapeHtml = (s) => String(s ?? "")
    .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
    .replace(/"/g,"&quot;").replace(/'/g,"&#039;");
  const showToast = (kind, title, message) => {
    if (!toastHost) return alert(message || title || "");
    const cls = {success:"bg-success text-white",warning:"bg-warning",danger:"bg-danger text-white",info:"bg-primary text-white"}[kind] || "bg-dark text-white";
    const el = document.createElement("div");
    el.className = "toast align-items-center border-0 shadow overflow-hidden";
    el.style.borderRadius = "12px";
    el.innerHTML = `
      <div class="toast-header ${cls}">
        <strong class="me-auto">${escapeHtml(title || "")}</strong>
        <button type="button" class="btn-close btn-close-white ms-2 mb-1" data-bs-dismiss="toast"></button>
      </div>
      <div class="toast-body">${escapeHtml(message || "")}</div>`;
    toastHost.appendChild(el);
    new bootstrap.Toast(el, { delay: 3200, autohide: true }).show();
  };
  const ensureOk = async (res, fb) => {
    const ct = res.headers.get("content-type") || "";
    if (res.ok) {
      if (res.status === 204 || !ct.includes("application/json")) return {};
      try { return await res.json(); } catch { return {}; }
    }
    let msg = fb || `HTTP ${res.status}`;
    try {
      if (ct.includes("application/json")) {
        const j = await res.json(); msg = j.message || j.detail || msg;
      } else {
        const t = await res.text(); if (t) msg = t;
      }
    } catch {}
    throw new Error(msg);
  };
  const extractArr = (data) =>
    Array.isArray(data) ? data : (Array.isArray(data?.items) ? data.items : (Array.isArray(data?.results) ? data.results : []));

  // API
  const listDepts = async () => {
    const res = await fetch(API.depts, { headers:{Accept:"application/json"} });
    const data = await ensureOk(res, "โหลดประเภทนักศึกษาไม่สำเร็จ");
    return extractArr(data)
      .map(x => ({ id: Number(x.id ?? x.pk ?? x.value), type: String(x.type ?? x.name ?? x.label ?? "")}))
      .filter(x=>x.id);
  };

  // ✅ แข็งแรงขึ้น: สร้าง text = "วัน HH:MM-HH:MM" แม้ end ไม่มี → บวก 60 นาทีให้
  const listSlots = async () => {
    const res = await fetch(API.slots, { headers:{Accept:"application/json"} });
    const data = await ensureOk(res, "โหลดคาบเวลาไม่สำเร็จ");
    return extractArr(data).map(x => {
      const id = Number(x.id ?? x.pk ?? x.value);

      // day
      const day = String(x.day ?? x.weekday ?? x.weekday_th ?? x.week ?? "")
                  || (typeof x.text === "string" ? x.text.split(" ")[0] : "")
                  || (typeof x.time_text === "string" ? x.time_text.split(" ")[0] : "");

      // ดึง start / end จากหลายชื่อฟิลด์
      const startRaw = x.start ?? x.start_time ?? x.time_start ?? x.begin ?? x.from ?? x.startAt ?? x.start_at;
      const endRaw   = x.end   ?? x.end_time   ?? x.time_end   ?? x.finish ?? x.to   ?? x.endAt   ?? x.end_at;

      // ถ้า text (หรือ time_text) มีรูปแบบ "HH:MM-HH:MM" ให้ parse เป็น fallback
      const txt = String(x.text ?? x.time_text ?? x.name ?? "");
      const m = txt.match(/(\d{1,2}:\d{2})(?::\d{2})?\s*-\s*(\d{1,2}:\d{2})(?::\d{2})?/);

      const startStr = (typeof startRaw === "string" && startRaw) ? startRaw : (m ? m[1] : "");
      let   endStr   = (typeof endRaw   === "string" && endRaw)   ? endRaw   : (m ? m[2] : "");

      // ถ้าไม่มี end แต่มี start → สมมุติ 60 นาที (คาบมาตรฐาน)
      if (!endStr && startStr) {
        const t = parseTime(startStr);
        if (t) endStr = addMinutes(t, 60);
      }

      // ตัดวินาทีออกให้เป็น HH:MM
      const ss = parseTime(startStr);
      const es = parseTime(endStr);
      const startHHMM = ss ? `${fmt2(ss.h)}:${fmt2(ss.m)}` : "";
      const endHHMM   = es ? `${fmt2(es.h)}:${fmt2(es.m)}` : "";

      // สร้างข้อความแสดงผล
      const text =
        day && startHHMM && endHHMM ? `${day} ${startHHMM}-${endHHMM}` :
        (txt || `${day} ${startHHMM}${endHHMM ? "-" + endHHMM : ""}`).trim();

      return { id, day, startMin: ss ? (ss.h*60+ss.m) : toMin(startHHMM), text };
    }).filter(x => x.id);
  };

  const listGroupAllows = async () => {
    const res = await fetch(API.list, { headers:{Accept:"application/json"} });
    const data = await ensureOk(res, "โหลดข้อมูลไม่สำเร็จ");
    return extractArr(data).map(x => ({
      id: Number(x.id ?? x.pk),
      dept: Number(x.dept ?? x.ga_dept_id ?? x.group_type ?? x.group_type_id),
      slot: Number(x.slot ?? x.ga_slot_id ?? x.timeslot ?? x.timeslot_id),
      dept_name: x.dept_name ?? x.type_name ?? "",
      slot_text: x.slot_text ?? x.time_text ?? "",
    })).filter(x=>x.id);
  };
  const createGA = async ({dept, slot}) => {
    const res = await fetch(API.add, {
      method:"POST",
      headers:{ "Content-Type":"application/json","X-CSRFToken":getCSRF(), Accept:"application/json" },
      body: JSON.stringify({ dept, slot })
    });
    return ensureOk(res, "เพิ่มข้อมูลไม่สำเร็จ");
  };
  const updateGA = async (id, {dept, slot}) => {
    const res = await fetch(API.update(id), {
      method:"PUT",
      headers:{ "Content-Type":"application/json","X-CSRFToken":getCSRF(), Accept:"application/json" },
      body: JSON.stringify({ dept, slot })
    });
    return ensureOk(res, "แก้ไขข้อมูลไม่สำเร็จ");
  };
  const deleteGA = async (id) => {
    const res = await fetch(API.del(id), { method:"DELETE", headers:{ "X-CSRFToken":getCSRF(), Accept:"application/json" } });
    await ensureOk(res, "ลบข้อมูลไม่สำเร็จ");
  };
  const deleteAllGA = async () => {
    const res = await fetch(API.delAll, { method:"DELETE", headers:{ "X-CSRFToken":getCSRF(), Accept:"application/json" } });
    await ensureOk(res, "ลบทั้งหมดไม่สำเร็จ");
  };

  // Caches
  let cache = [], deptCache = [], slotCache = [];
  const deptText = (id) => deptCache.find(t => +t.id === +id)?.type || "";
  const slotText = (id) => slotCache.find(t => +t.id === +id)?.text || "";

  const fillSelects = () => {
    const deptOpts = `<option value="">-- เลือกภาค --</option>` +
      deptCache.map(d => `<option value="${d.id}">${escapeHtml(d.type)}</option>`).join("");

    const sortedSlots = [...slotCache].sort((a,b) =>
      (dayIndex(a.day) - dayIndex(b.day)) ||
      (a.startMin - b.startMin) ||
      String(a.text).localeCompare(String(b.text))
    );
    const slotOpts = `<option value="">-- เลือกคาบ --</option>` +
      sortedSlots.map(s => `<option value="${s.id}">${escapeHtml(s.text)}</option>`).join("");

    deptSel.innerHTML = deptOpts;   if (editDept) editDept.innerHTML = deptOpts;
    slotSel.innerHTML = slotOpts;   if (editSlot) editSlot.innerHTML = slotOpts;
  };

  const slotOrderInfo = (row) => {
    const sc = slotCache.find(s => +s.id === +row.slot);
    if (sc) return { dayIdx: dayIndex(sc.day), startMin: sc.startMin, txt: sc.text };
    const t = String(row.slot_text || "");
    const day = t.split(" ")[0] || "";
    const m = t.match(/(\d{1,2}):(\d{2})(?::\d{2})?/);
    const smin = m ? (+m[1]*60 + +m[2]) : 99999;
    return { dayIdx: dayIndex(day), startMin: smin, txt: t };
  };

  const renderTable = (items) => {
    if (!items?.length) {
      tbody.innerHTML = `<tr class="empty-row"><td colspan="3" class="text-center text-muted">ไม่มีข้อมูลคาบที่เรียนได้</td></tr>`;
      return;
    }
    const sorted = [...items].sort((a,b) => {
      const A = slotOrderInfo(a), B = slotOrderInfo(b);
      return (A.dayIdx - B.dayIdx) || (A.startMin - B.startMin) || String(A.txt).localeCompare(String(B.txt));
    });
    tbody.innerHTML = sorted.map(({ id, dept, slot, dept_name, slot_text }) => `
      <tr data-id="${id}">
        <td>${escapeHtml(dept_name || deptText(dept) || String(dept || ""))}</td>
        <td>${escapeHtml(slot_text || slotText(slot) || String(slot || ""))}</td>
        <td class="d-flex justify-content-center gap-2">
          <button type="button" class="btn-warning-gradient btn-edit">แก้ไข</button>
          <button type="button" class="btn-danger-gradient btn-delete">ลบ</button>
        </td>
      </tr>`).join("");
  };

  const refresh = async () => {
    try {
      [deptCache, slotCache] = await Promise.all([listDepts(), listSlots()]);
      fillSelects();
      cache = await listGroupAllows();
      renderTable(cache);
    } catch (e) {
      showToast("danger","โหลดข้อมูลล้มเหลว", e.message || "เกิดข้อผิดพลาด");
      renderTable([]);
    }
  };
  refresh();

  // Create
  form?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const dept = +deptSel.value || 0;
    const slot = +slotSel.value || 0;
    if (!dept) return showToast("warning","ข้อมูลไม่ครบ","กรุณาเลือกภาค/ประเภทนักศึกษา");
    if (!slot) return showToast("warning","ข้อมูลไม่ครบ","กรุณาเลือกคาบเวลา");
    if (cache.find(x => +x.dept === dept && +x.slot === slot)) {
      return showToast("warning","ข้อมูลซ้ำ","ภาคนี้มีคาบดังกล่าวอยู่แล้ว");
    }
    try {
      btnSubmit.disabled = true;
      await createGA({ dept, slot });
      form.reset();
      showToast("success","เพิ่มสำเร็จ","บันทึกคาบที่เรียนได้แล้ว");
      await refresh();
    } catch (err) {
      showToast("danger","เพิ่มไม่สำเร็จ", err.message || "เกิดข้อผิดพลาด");
    } finally {
      btnSubmit.disabled = false;
    }
  });

  // Row actions
  tbody?.addEventListener("click", (e) => {
    const tr = e.target.closest("tr"); if (!tr) return;
    const id = tr.dataset.id;
    const row = cache.find(x => String(x.id) === String(id)); if (!row) return;

    if (e.target.closest(".btn-delete")) {
      if (bsDel) { pendingDeleteId = id; bsDel.show(); }
      else if (confirm("ยืนยันการลบรายการนี้?")) btnConfirmDelete.click();
      return;
    }
    if (e.target.closest(".btn-edit")) {
      if (!bsEdit) return showToast("warning","ไม่พบหน้าต่างแก้ไข","โปรดตรวจสอบ modal แก้ไข");
      editId.value = row.id;
      editDept.value = String(row.dept);
      editSlot.value = String(row.slot);
      bsEdit.show();
    }
  });

  // Save edit
  btnSave?.addEventListener("click", async () => {
    const id = editId.value;
    const dept = +editDept.value || 0;
    const slot = +editSlot.value || 0;
    if (!dept) return showToast("warning","ข้อมูลไม่ครบ","กรุณาเลือกภาค/ประเภทนักศึกษา");
    if (!slot) return showToast("warning","ข้อมูลไม่ครบ","กรุณาเลือกคาบเวลา");
    if (cache.find(x => String(x.id)!==String(id) && +x.dept===dept && +x.slot===slot)) {
      return showToast("warning","ข้อมูลซ้ำ","ภาคนี้มีคาบดังกล่าวอยู่แล้ว");
    }
    try {
      btnSave.disabled = true;
      await updateGA(id, { dept, slot });
      bsEdit?.hide();
      showToast("success","แก้ไขสำเร็จ","บันทึกข้อมูลเรียบร้อย");
      await refresh();
    } catch (err) {
      showToast("danger","แก้ไขไม่สำเร็จ", err.message || "เกิดข้อผิดพลาด");
    } finally {
      btnSave.disabled = false;
    }
  });

  // Delete all
  btnDeleteAll?.addEventListener("click", () => {
    if (bsDelAll) bsDelAll.show();
    else if (confirm("ยืนยันการลบทั้งหมด?")) btnConfirmDeleteAll?.click();
  });
  btnConfirmDeleteAll?.addEventListener("click", async () => {
    try {
      btnConfirmDeleteAll.disabled = true;
      await deleteAllGA();
      bsDelAll?.hide();
      showToast("success","ลบทั้งหมดสำเร็จ","ลบคาบที่เรียนได้ทั้งหมดแล้ว");
      await refresh();
    } catch (err) {
      showToast("danger","ลบทั้งหมดไม่สำเร็จ", err.message || "เกิดข้อผิดพลาด");
    } finally {
      btnConfirmDeleteAll.disabled = false;
    }
  });

  // Confirm delete single
  btnConfirmDelete?.addEventListener("click", async () => {
    if (!pendingDeleteId) return;
    try {
      btnConfirmDelete.disabled = true;
      await deleteGA(pendingDeleteId);
      bsDel?.hide();
      showToast("success","ลบสำเร็จ","รายการถูกลบแล้ว");
      pendingDeleteId = null;
      await refresh();
    } catch (err) {
      showToast("danger","ลบไม่สำเร็จ", err.message || "เกิดข้อผิดพลาด");
    } finally {
      btnConfirmDelete.disabled = false;
    }
  });
});
