// /static/js/room.js
document.addEventListener("DOMContentLoaded", () => {
  /* ===== CSRF ===== */
  const csrftoken = (() => {
    const m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  })();

  /* ===== Fetch helpers (รองรับ non-JSON/204) ===== */
  const headersJson = () => ({ "Content-Type": "application/json", "X-CSRFToken": csrftoken, Accept: "application/json" });
  async function ensureOk(res, fallback) {
    const ct = res.headers.get("content-type") || "";
    if (res.ok) {
      if (res.status === 204 || !ct.includes("application/json")) return {};
      try { return await res.json(); } catch { return {}; }
    }
    let msg = fallback || `HTTP ${res.status}`;
    try {
      if (ct.includes("application/json")) {
        const j = await res.json();
        msg = j.message || j.detail || msg;
      } else { msg = (await res.text()) || msg; }
    } catch {}
    throw new Error(msg);
  }

  /* ===== API endpoints (อ้างอิงตามโปรเจกต์เดิม) ===== */
  const API = {
    listTypes: "/api/roomtype/list/",
    list:      "/api/room/list/",
    add:       "/api/room/add/",
    del:       (id) => `/api/room/delete/${id}/`,
    delAll:    "/api/room/delete-all/",
  };

  /* ===== Elements ===== */
  const form = document.getElementById("roomForm");
  const nameInput = document.getElementById("room_name");
  const typeSelect = document.getElementById("room_type_select");
  const btnSubmit = document.getElementById("btnAddRoom");
  const btnCancel = document.getElementById("btnCancelRoomEdit");
  const tbody = document.getElementById("roomTableBody");
  const btnDeleteAll = document.getElementById("btnDeleteAllRoom");
  const toastHost = document.getElementById("toastHost");

  // edit modal
  const editEl = document.getElementById("editRoomModal");
  const bsEdit = editEl ? new bootstrap.Modal(editEl) : null;
  const editId = document.getElementById("edit_room_id");
  const editName = document.getElementById("edit_room_name");
  const editType = document.getElementById("edit_room_type");
  const btnSave = document.getElementById("btnSaveRoom");

  // delete-one modal
  const delEl = document.getElementById("confirmDeleteModal");
  const bsDel = delEl ? new bootstrap.Modal(delEl) : null;
  const delRoomName = document.getElementById("del_room_name");
  const btnConfirmDelete = document.getElementById("btnConfirmDelete");
  let pendingDeleteId = null;

  // delete-all modal
  const delAllEl = document.getElementById("confirmDeleteAllModal");
  const bsDelAll = delAllEl ? new bootstrap.Modal(delAllEl) : null;
  const btnConfirmDeleteAll = document.getElementById("btnConfirmDeleteAll");

  /* ===== Toast ===== */
  function showToast(kind, title, message) {
    if (!toastHost) { alert(message || title || ""); return; }
    const map = { success:"bg-success text-white", warning:"bg-warning", danger:"bg-danger text-white", info:"bg-primary text-white" };
    const cls = map[kind] || "bg-dark text-white";
    const el = document.createElement("div");
    el.className = "toast align-items-center border-0 shadow overflow-hidden";
    el.style.borderRadius = "12px";
    el.innerHTML = `
      <div class="toast-header ${cls}">
        <strong class="me-auto">${escapeHtml(title||"")}</strong>
        <button type="button" class="btn-close btn-close-white ms-2" data-bs-dismiss="toast"></button>
      </div>
      <div class="toast-body">${escapeHtml(message||"")}</div>`;
    toastHost.appendChild(el);
    const t = new bootstrap.Toast(el, { delay: 2500 });
    t.show();
    el.addEventListener("hidden.bs.toast", () => el.remove());
  }
  const escapeHtml = (s) => String(s ?? "")
    .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
    .replace(/"/g,"&quot;").replace(/'/g,"&#039;");

  /* ===== State ===== */
  let cache = []; // [{id,name,type_id,type_name}]

  /* ===== Load room types (ฟอร์ม + modal edit) ===== */
  async function loadRoomTypes() {
    const res = await fetch(API.listTypes);
    const data = await ensureOk(res, "โหลดประเภทห้องไม่สำเร็จ");
    const list = Array.isArray(data.items) ? data.items : [];
    typeSelect.innerHTML = `<option value="">-- เลือกประเภทห้อง --</option>` + list.map(x=>`<option value="${x.id}">${escapeHtml(x.name)}</option>`).join("");
    if (editType) {
      editType.innerHTML = `<option value="">-- เลือกประเภทห้อง --</option>` + list.map(x=>`<option value="${x.id}">${escapeHtml(x.name)}</option>`).join("");
    }
  }

  /* ===== Render table ===== */
  function render() {
    if (!cache.length) {
      tbody.innerHTML = `<tr class="empty-row"><td colspan="3" class="text-center text-muted">ไม่มีข้อมูลห้องเรียน</td></tr>`;
      return;
    }
    const rows = [...cache]
      .sort((a,b)=>Number(b.id)-Number(a.id)) // ใหม่สุดอยู่บน
      .map(r => `
      <tr data-id="${r.id}">
        <td>${escapeHtml(r.name)}</td>
        <td>${escapeHtml(r.type_name || r.room_type_name || "")}</td>
        <td class="text-center">
          <button class="btn-warning-gradient btn-sm me-2 btn-edit">แก้ไข</button>
          <button class="btn-danger-gradient btn-sm btn-delete">ลบ</button>
        </td>
      </tr>
    `).join("");
    tbody.innerHTML = rows;
  }

  async function refresh() {
    const res = await fetch(API.list);
    const data = await ensureOk(res, "โหลดห้องเรียนไม่สำเร็จ");
    cache = Array.isArray(data.items) ? data.items : [];
    render();
  }

  /* ===== Duplicate rules =====
     DB บังคับ unique ที่ 'name' ดังนั้นต้องกันซ้ำจากชื่ออย่างเดียว
  */
  function isDupName(name, exceptId=null) {
    const n = String(name).trim();
    return cache.some(r => String(r.name).trim() === n && String(r.id) !== String(exceptId ?? ""));
  }

  /* ===== Create ===== */
  form?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = (nameInput.value || "").trim();
    const typeId = typeSelect.value;

    if (!name) return showToast("warning","ข้อมูลไม่ครบ","กรุณากรอกชื่อห้องเรียน");
    if (!typeId) return showToast("warning","ข้อมูลไม่ครบ","กรุณาเลือกประเภทห้อง");
    if (isDupName(name)) return showToast("warning","ชื่อห้องซ้ำ","มีชื่อห้องนี้อยู่แล้ว");

    try {
      btnSubmit.disabled = true;
      btnSubmit.innerHTML = "กำลังบันทึก...";

      const res = await fetch(API.add, {
        method: "POST",
        headers: headersJson(),
        body: JSON.stringify({ name, type: Number(typeId) }),
      });
      await ensureOk(res, "บันทึกไม่สำเร็จ");
      form.reset();
      showToast("success","เพิ่มสำเร็จ","บันทึกข้อมูลเรียบร้อย");
      await refresh();
    } catch (err) {
      const m = (err.message||"").toLowerCase();
      if (m.includes("duplicate") || m.includes("unique")) {
        showToast("danger","เพิ่มไม่สำเร็จ","ชื่อห้องนี้มีอยู่แล้ว");
      } else {
        showToast("danger","เพิ่มไม่สำเร็จ", err.message || "");
      }
    } finally {
      btnSubmit.disabled = false;
      btnSubmit.innerHTML = '<i class="bi bi-plus-lg me-2"></i><span>เพิ่มข้อมูล</span>';
    }
  });

  /* ===== Row actions ===== */
  tbody?.addEventListener("click", (e) => {
    const tr = e.target.closest("tr");
    if (!tr) return;
    const id = tr.getAttribute("data-id");
    const row = cache.find(x => String(x.id) === String(id));
    if (!row) return;

    // แก้ไข
    if (e.target.closest(".btn-edit")) {
      editId.value = row.id;
      editName.value = row.name;
      const tid = row.type_id ?? row.room_type_id ?? row.type;
      editType.value = (tid != null && editType.querySelector(`option[value="${tid}"]`)) ? String(tid) : "";
      if (!editType.value) {
        for (const opt of [...editType.options]) {
          if (opt.text.trim() === (row.type_name||row.room_type_name||"").trim()) { editType.value = opt.value; break; }
        }
      }
      bsEdit?.show();
      return;
    }

    // ลบเดี่ยว
    if (e.target.closest(".btn-delete")) {
      pendingDeleteId = id;
      delRoomName.textContent = row.name || "";
      bsDel?.show();
    }
  });

  // save edit
  btnSave?.addEventListener("click", async () => {
    const id = editId.value;
    const name = (editName.value || "").trim();
    const typeId = editType.value;

    if (!name) return showToast("warning","ข้อมูลไม่ครบ","กรุณากรอกชื่อห้องเรียน");
    if (!typeId) return showToast("warning","ข้อมูลไม่ครบ","กรุณาเลือกประเภทห้อง");
    if (isDupName(name, id)) return showToast("warning","ชื่อห้องซ้ำ","มีชื่อห้องนี้อยู่แล้ว");

    try {
      btnSave.disabled = true;
      const res = await fetch(API.add, {
        method: "POST",
        headers: headersJson(),
        body: JSON.stringify({ id: Number(id), name, type: Number(typeId) }),
      });
      await ensureOk(res, "อัปเดตไม่สำเร็จ");
      bsEdit?.hide();
      showToast("success","แก้ไขสำเร็จ","บันทึกข้อมูลเรียบร้อย");
      await refresh();
    } catch (err) {
      const m = (err.message||"").toLowerCase();
      if (m.includes("duplicate") || m.includes("unique")) {
        showToast("danger","แก้ไขไม่สำเร็จ","ชื่อห้องนี้มีอยู่แล้ว");
      } else {
        showToast("danger","แก้ไขไม่สำเร็จ", err.message || "");
      }
    } finally {
      btnSave.disabled = false;
    }
  });

  // confirm delete (single)
  btnConfirmDelete?.addEventListener("click", async () => {
    if (!pendingDeleteId) return;
    try {
      btnConfirmDelete.disabled = true;
      const res = await fetch(API.del(pendingDeleteId), { method:"DELETE", headers:{ "X-CSRFToken": csrftoken, Accept:"application/json" } });
      await ensureOk(res, "ลบไม่สำเร็จ");
      bsDel?.hide();
      showToast("success","ลบสำเร็จ","รายการถูกลบแล้ว");
      await refresh();
    } catch (err) {
      showToast("danger","ลบไม่สำเร็จ", err.message || "");
    } finally {
      btnConfirmDelete.disabled = false;
      pendingDeleteId = null;
    }
  });

  // delete-all
  btnDeleteAll?.addEventListener("click", () => bsDelAll?.show());
  btnConfirmDeleteAll?.addEventListener("click", async () => {
    try {
      btnConfirmDeleteAll.disabled = true;
      const res = await fetch(API.delAll, { method:"DELETE", headers:{ "X-CSRFToken": csrftoken, Accept:"application/json" } });
      await ensureOk(res, "ลบทั้งหมดไม่สำเร็จ");
      bsDelAll?.hide();
      showToast("success","ลบทั้งหมดสำเร็จ","ลบข้อมูลห้องทั้งหมดแล้ว");
      await refresh();
    } catch (err) {
      showToast("danger","ลบทั้งหมดไม่สำเร็จ", err.message || "");
    } finally {
      btnConfirmDeleteAll.disabled = false;
    }
  });

  /* ===== Init ===== */
  (async () => {
    await loadRoomTypes();
    await refresh();
  })();
});
