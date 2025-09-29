// /static/js/roomtype.js
document.addEventListener("DOMContentLoaded", () => {
  /* ===== API ===== */
  const API = {
    list:  "/api/roomtype/list/",
    add:   "/api/roomtype/add/",                  // POST {name} | อัปเดต: POST {id,name}
    del:   (id) => `/api/roomtype/delete/${id}/`, // DELETE
    delAll:"/api/roomtype/delete-all/",           // DELETE
  };

  /* ===== Elements ===== */
  const form = document.getElementById("roomTypeForm");
  const nameInput = document.getElementById("roomtype_name");
  const tbody = document.getElementById("roomTypeTableBody");
  const btnSubmit = document.getElementById("btnAddRoomType");
  const btnCancel = document.getElementById("btnCancelRoomTypeEdit");
  const btnDeleteAll = document.getElementById("btnDeleteAllRoomType");
  const toastHost = document.getElementById("toastHost");

  // Edit modal
  const editEl = document.getElementById("editRoomTypeModal");
  const bsEdit = editEl ? new bootstrap.Modal(editEl) : null;
  const editId = document.getElementById("edit_rt_id");
  const editName = document.getElementById("edit_rt_name");
  const btnSave = document.getElementById("btnSaveRoomType");

  // Delete (single) modal
  const delModalEl = document.getElementById("confirmDeleteModal");
  const bsDel = delModalEl ? new bootstrap.Modal(delModalEl) : null;
  const delItemName = document.getElementById("del_item_name");
  const btnConfirmDelete = document.getElementById("btnConfirmDelete");
  let pendingDeleteId = null;

  // Delete-all modal
  const delAllModalEl = document.getElementById("confirmDeleteAllModal");
  const bsDelAll = delAllModalEl ? new bootstrap.Modal(delAllModalEl) : null;
  const btnConfirmDeleteAll = document.getElementById("btnConfirmDeleteAll");

  /* ===== Helpers ===== */
  const getCSRF = () =>
    document.querySelector('input[name="csrfmiddlewaretoken"]')?.value || "";

  const jsonHeaders = () => ({
    "Content-Type": "application/json",
    "X-CSRFToken": getCSRF(),
    Accept: "application/json",
  });

  // แปล error ของ DB ให้เป็นข้อความอ่านง่าย
  const friendlyError = (rawMsg) => {
    const m = String(rawMsg || "").toLowerCase();
    if (m.includes("duplicate entry") && m.includes("key 'name'")) {
      return "ชื่อประเภทห้องนี้มีอยู่แล้ว";
    }
    return rawMsg || "เกิดข้อผิดพลาด";
  };

  // รองรับ response ที่เป็น 204 / หรือไม่ใช่ JSON
  const ensureOk = async (res, fallbackMsg) => {
    const ct = res.headers.get("content-type") || "";
    if (res.ok) {
      if (res.status === 204 || !ct.includes("application/json")) return {};
      try { return await res.json(); } catch { return {}; }
    }
    let msg = fallbackMsg || `HTTP ${res.status}`;
    try {
      if (ct.includes("application/json")) {
        const j = await res.json();
        msg = j.message || j.detail || msg;
      } else {
        const t = await res.text();
        if (t) msg = t;
      }
    } catch {}
    throw new Error(msg);
  };

  const escapeHtml = (s) => String(s ?? "")
    .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
    .replace(/"/g,"&quot;").replace(/'/g,"&#039;");

  const showToast = (kind, title, message) => {
    if (!toastHost) { alert(message || title || ""); return; }
    const cls = {
      success:"bg-success text-white",
      warning:"bg-warning",
      danger:"bg-danger text-white",
      info:"bg-primary text-white"
    }[kind] || "bg-dark text-white";
    const el = document.createElement("div");
    el.className = "toast align-items-center border-0 shadow overflow-hidden";
    el.style.borderRadius = "12px";
    el.innerHTML = `
      <div class="toast-header ${cls}">
        <strong class="me-auto">${escapeHtml(title||"")}</strong>
        <button type="button" class="btn-close btn-close-white ms-2 mb-1" data-bs-dismiss="toast"></button>
      </div>
      <div class="toast-body">${escapeHtml(message||"")}</div>`;
    toastHost.appendChild(el);
    const t = new bootstrap.Toast(el, { delay: 2500 });
    t.show();
    el.addEventListener("hidden.bs.toast", () => el.remove());
  };

  /* ===== Data cache + render ===== */
  let cache = []; // [{id,name}]
  const isDup = (name, exceptId=null) => {
    const n = String(name || "").trim();
    return cache.some(r => String(r.name).trim() === n && String(r.id) !== String(exceptId ?? ""));
  };

  const render = () => {
    if (!tbody) return;
    if (!cache.length) {
      tbody.innerHTML = `<tr class="empty-row"><td colspan="2" class="text-center text-muted">ไม่มีข้อมูลประเภทห้องเรียน</td></tr>`;
      return;
    }
    // ใหม่สุดอยู่บน
    const rows = [...cache].sort((a,b) => Number(b.id) - Number(a.id)).map(r => `
      <tr data-id="${r.id}">
        <td>${escapeHtml(r.name)}</td>
        <td class="text-center">
          <button class="btn-warning-gradient btn-sm me-2 btn-edit">แก้ไข</button>
          <button class="btn-danger-gradient btn-sm btn-delete">ลบ</button>
        </td>
      </tr>
    `).join("");
    tbody.innerHTML = rows;
  };

  const refresh = async () => {
    const res = await fetch(API.list);
    const data = await ensureOk(res, "ไม่สามารถโหลดรายการได้");
    cache = Array.isArray(data.items) ? data.items : [];
    render();
  };

  /* ===== CRUD ===== */
  async function createRT(name) {
    const res = await fetch(API.add, {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify({ name: String(name || "").trim() }),
    });
    await ensureOk(res, "บันทึกไม่สำเร็จ");
  }

  // อัปเดต: ใช้ POST /api/roomtype/add/ พร้อม id (views.update_or_create)
  async function updateRT(id, name) {
    const res = await fetch(API.add, {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify({ id: Number(id), name: String(name || "").trim() }),
    });
    await ensureOk(res, "อัปเดตไม่สำเร็จ");
  }

  async function deleteRT(id) {
    const res = await fetch(API.del(id), { method: "DELETE", headers: jsonHeaders() });
    await ensureOk(res, "ลบไม่สำเร็จ");
  }

  async function deleteAllRT() {
    const res = await fetch(API.delAll, { method: "DELETE", headers: jsonHeaders() });
    await ensureOk(res, "ลบทั้งหมดไม่สำเร็จ");
  }

  /* ===== Events ===== */
  // เพิ่มใหม่
  form?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = (nameInput.value || "").trim();
    if (!name) return showToast("warning","ข้อมูลไม่ครบ","กรุณากรอกชื่อประเภทห้อง");
    if (isDup(name)) return showToast("warning","เพิ่มไม่สำเร็จ","ชื่อประเภทห้องนี้มีอยู่แล้ว");

    try {
      btnSubmit.disabled = true;
      const old = btnSubmit.innerHTML;
      btnSubmit.innerHTML = "กำลังบันทึก...";
      await createRT(name);
      form.reset();
      showToast("success","เพิ่มสำเร็จ","บันทึกข้อมูลเรียบร้อย");
      await refresh();
      btnSubmit.innerHTML = old;
    } catch (err) {
      showToast("danger","เพิ่มไม่สำเร็จ", friendlyError(err.message));
    } finally {
      btnSubmit.disabled = false;
    }
  });

  // แก้ไข / ลบ รายบรรทัด
  tbody?.addEventListener("click", (e) => {
    const tr = e.target.closest("tr");
    if (!tr) return;
    const id = tr.dataset.id;
    const row = cache.find(x => String(x.id) === String(id));
    if (!row) return;

    if (e.target.closest(".btn-edit")) {
      if (bsEdit) {
        editId.value = row.id;
        editName.value = row.name;
        bsEdit.show();
      }
      return;
    }
    if (e.target.closest(".btn-delete")) {
      pendingDeleteId = id;
      delItemName.textContent = row.name || "";
      bsDel?.show();
    }
  });

  // บันทึกแก้ไข
  btnSave?.addEventListener("click", async () => {
    const id = editId.value;
    const newName = (editName.value || "").trim();

    if (!newName) return showToast("warning","ข้อมูลไม่ครบ","กรุณากรอกชื่อประเภทห้อง");

    const row = cache.find(x => String(x.id) === String(id));
    if (row && row.name.trim() === newName) {
      bsEdit?.hide();
      return showToast("info","ไม่มีการเปลี่ยนแปลง","ข้อมูลเหมือนเดิม");
    }
    if (isDup(newName, id)) return showToast("warning","แก้ไขไม่สำเร็จ","ชื่อประเภทห้องนี้มีอยู่แล้ว");

    try {
      btnSave.disabled = true;
      const old = btnSave.textContent;
      btnSave.textContent = "กำลังบันทึก...";
      await updateRT(id, newName);
      bsEdit?.hide();
      showToast("success","แก้ไขสำเร็จ","บันทึกข้อมูลเรียบร้อย");
      await refresh();
      btnSave.textContent = old;
    } catch (err) {
      showToast("danger","แก้ไขไม่สำเร็จ", friendlyError(err.message));
    } finally {
      btnSave.disabled = false;
    }
  });

  // ลบเดี่ยว
  btnConfirmDelete?.addEventListener("click", async () => {
    if (!pendingDeleteId) return;
    try {
      btnConfirmDelete.disabled = true;
      await deleteRT(pendingDeleteId);
      bsDel?.hide();
      showToast("success","ลบสำเร็จ","รายการถูกลบแล้ว");
      await refresh();
    } catch (err) {
      showToast("danger","ลบไม่สำเร็จ", friendlyError(err.message));
    } finally {
      btnConfirmDelete.disabled = false;
      pendingDeleteId = null;
    }
  });

  // ลบทั้งหมด
  btnDeleteAll?.addEventListener("click", () => bsDelAll?.show());
  btnConfirmDeleteAll?.addEventListener("click", async () => {
    try {
      btnConfirmDeleteAll.disabled = true;
      await deleteAllRT();
      bsDelAll?.hide();
      showToast("success","ลบทั้งหมดสำเร็จ","ลบประเภทห้องเรียนทั้งหมดแล้ว");
      await refresh();
    } catch (err) {
      showToast("danger","ลบทั้งหมดไม่สำเร็จ", friendlyError(err.message));
    } finally {
      btnConfirmDeleteAll.disabled = false;
    }
  });

  /* ===== init ===== */
  refresh().catch(err => showToast("danger","โหลดข้อมูลไม่สำเร็จ", err.message || ""));
});
