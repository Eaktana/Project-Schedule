// /static/js/grouptype.js
document.addEventListener("DOMContentLoaded", () => {
  // ---- API (เรียก list แบบ order=-id ให้รายการใหม่อยู่บนสุด) ----
  const API = {
    list:  "/api/grouptype/list/?order=-id",
    add:   "/api/grouptype/add/",
    del:   (id) => `/api/grouptype/delete/${id}/`,
    delAll:"/api/grouptype/delete-all/",
    update:(id) => `/api/grouptype/update/${id}/`, // ถ้ามี endpoint แก้ไข
  };

  // ---- Elements ----
  const form = document.getElementById("groupTypeForm");
  const nameInput = document.getElementById("student_type");
  const tbody = document.getElementById("groupTypeTableBody");
  const btnSubmit = document.getElementById("btnAddGroupType");
  const btnDeleteAll = document.getElementById("btnDeleteAllGroupType");
  const toastHost = document.getElementById("toastHost");

  // Edit modal
  const editEl = document.getElementById("editGroupTypeModal");
  const bsEdit = editEl ? new bootstrap.Modal(editEl) : null;
  const modalId = document.getElementById("edit_gt_id");
  const modalName = document.getElementById("edit_gt_name");
  const btnSave = document.getElementById("btnSaveGroupType");

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

  // ---- Helpers ----
  const getCSRF = () => {
    const el = document.querySelector('input[name="csrfmiddlewaretoken"]');
    return el ? el.value : "";
  };
  const jsonHeaders = () => ({
    "Content-Type": "application/json",
    "X-CSRFToken": getCSRF(),
    Accept: "application/json",
  });
  const parseJSONSafe = async (res) => {
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) return res.json();
    const text = await res.text();
    return { status: "error", message: text || `HTTP ${res.status}` };
  };
  const ensureOk = async (res, fb) => {
    if (res.ok) return;
    const data = await parseJSONSafe(res);
    throw new Error(data?.message || data?.detail || fb || `HTTP ${res.status}`);
  };
  const escapeHtml = (s) =>
    String(s ?? "")
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const setLoading = (btn, on) => {
    if (!btn) return;
    btn.disabled = on;
    let sp = btn.querySelector(".spinner-border");
    if (on && !sp) {
      sp = document.createElement("span");
      sp.className = "spinner-border spinner-border-sm ms-2";
      sp.setAttribute("role","status");
      sp.setAttribute("aria-hidden","true");
      btn.appendChild(sp);
    }
    if (!on && sp) sp.remove();
  };
  function showToast(kind, title, message) {
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
    new bootstrap.Toast(el, { delay: 3500, autohide: true }).show();
  }

  // ---- API calls ----
  const listGroupTypes = async () => {
    const res = await fetch(API.list, { headers: { Accept: "application/json" } });
    await ensureOk(res, "โหลดข้อมูลไม่สำเร็จ");
    const data = await res.json(); // {status:'success', items:[{id,type},...]}
    return Array.isArray(data?.items) ? data.items : [];
  };
  const createGroupType = async (name) => {
    const res = await fetch(API.add, {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify({ type: name }), // ไม่ส่ง id
    });
    await ensureOk(res, "เพิ่มข้อมูลไม่สำเร็จ");
    return res.json(); // ถ้าคืน item ก็จะใช้ต่อได้ด้านล่าง
  };
  const updateGroupType = async (id, name) => {
    const res = await fetch(API.update(id), {
      method: "PUT",
      headers: jsonHeaders(),
      body: JSON.stringify({ type: name }),
    });
    await ensureOk(res, "แก้ไขข้อมูลไม่สำเร็จ");
    return res.json();
  };
  const deleteGroupType = async (id) => {
    const res = await fetch(API.del(id), {
      method: "DELETE",
      headers: { "X-CSRFToken": getCSRF(), Accept: "application/json" },
    });
    await ensureOk(res, "ลบข้อมูลไม่สำเร็จ");
    return true;
  };
  const deleteAllGroupTypes = async () => {
    const res = await fetch(API.delAll, {
      method: "DELETE",
      headers: { "X-CSRFToken": getCSRF(), Accept: "application/json" },
    });
    await ensureOk(res, "ลบทั้งหมดไม่สำเร็จ");
    return true;
  };

  // ---- Render ----
  const rowHTML = ({ id, type }) => `
    <tr data-id="${id}">
      <td>${escapeHtml(type)}</td>
      <td class="d-flex justify-content-center gap-2">
        <button type="button" class="btn-warning-gradient btn-edit"
                data-id="${id}" data-name="${escapeHtml(type)}" title="แก้ไข">
          <span>แก้ไข</span>
        </button>
        <button type="button" class="btn-danger-gradient btn-delete" title="ลบ">
          <span>ลบ</span>
        </button>
      </td>
    </tr>
  `;
  const renderTable = (items) => {
    if (!tbody) return;
    if (!Array.isArray(items) || items.length === 0) {
      tbody.innerHTML = `
        <tr class="empty-row">
          <td colspan="2" class="text-center text-muted">ไม่มีข้อมูลประเภทนักศึกษา</td>
        </tr>`;
      return;
    }
    // API คืนมาลำดับ -id อยู่แล้ว ไม่ต้องจัดเรียงซ้ำ
    tbody.innerHTML = items.map(rowHTML).join("");
  };

  // ---- Cache + refresh ----
  let cache = [];
  const refresh = async () => {
    try {
      cache = await listGroupTypes(); // ได้ลิสต์ที่เรียง -id แล้ว
      renderTable(cache);
    } catch (e) {
      showToast("danger", "โหลดข้อมูลล้มเหลว", e.message || "เกิดข้อผิดพลาดในการโหลดข้อมูล");
    }
  };

  // ---- Init ----
  refresh();

  // ---- Events ----
  // เพิ่ม (ห้ามชื่อซ้ำ)
  form?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = nameInput.value.trim();
    if (!name) {
      showToast("warning", "ข้อมูลไม่ครบ", 'กรุณากรอก "ชื่อประเภทนักศึกษา"');
      return;
    }
    const norm = (s) => s.trim().toLowerCase();
    if (cache.find((x) => norm(x.type || "") === norm(name))) {
      showToast("warning", "ชื่อซ้ำ", `ประเภทนักศึกษา "${name}" มีอยู่แล้ว`);
      return;
    }
    try {
      setLoading(btnSubmit, true);
      const res = await createGroupType(name);
      form.reset();

      // ถ้า backend คืน {item:{id,type}} มาก็ prepend เลย
      const newItem = res?.item;
      if (newItem && newItem.id) {
        cache.unshift(newItem);
        renderTable(cache);
      } else {
        // ถ้าไม่ ก็ refresh (ยังคงได้ลำดับ -id)
        await refresh();
      }

      showToast("success", "เพิ่มสำเร็จ", `เพิ่ม "${name}" แล้ว`);
    } catch (e2) {
      showToast("warning", "เพิ่มไม่สำเร็จ", e2.message || "เกิดข้อผิดพลาดในการบันทึก");
    } finally {
      setLoading(btnSubmit, false);
    }
  });

  // แก้ไข/ลบ รายตัว
  tbody?.addEventListener("click", (e) => {
    const row = e.target.closest("tr");
    if (!row) return;
    const id = row.dataset.id;

    const editBtn = e.target.closest(".btn-edit");
    if (editBtn && bsEdit) {
      modalId.value = id;
      modalName.value = editBtn.dataset.name || row.children[0].textContent.trim();
      bsEdit.show();
      return;
    }

    const delBtn = e.target.closest(".btn-delete");
    if (delBtn && id && bsDel) {
      pendingDeleteId = id;
      delItemName.textContent = row.children[0]?.textContent.trim() || "";
      bsDel.show();
    }
  });

  // บันทึกแก้ไข
  btnSave?.addEventListener("click", async () => {
    const id = modalId.value;
    const name = modalName.value.trim();
    if (!name) {
      showToast("warning", "ข้อมูลไม่ครบ", 'กรุณากรอก "ชื่อประเภทนักศึกษา"');
      return;
    }
    const norm = (s) => s.trim().toLowerCase();
    if (cache.find((x) => String(x.id) !== String(id) && norm(x.type || "") === norm(name))) {
      showToast("warning", "ชื่อซ้ำ", `"${name}" ซ้ำกับรายการเดิม`);
      return;
    }
    try {
      btnSave.disabled = true;
      await updateGroupType(id, name);
      bsEdit?.hide();
      showToast("success", "แก้ไขสำเร็จ", `บันทึก "${name}" แล้ว`);
      await refresh();
    } catch (e2) {
      showToast("warning", "แก้ไขไม่สำเร็จ", e2.message || "เกิดข้อผิดพลาดในการแก้ไข");
    } finally {
      btnSave.disabled = false;
    }
  });

  // ลบทั้งหมด
  btnDeleteAll?.addEventListener("click", () => bsDelAll?.show());
  btnConfirmDeleteAll?.addEventListener("click", async () => {
    try {
      btnConfirmDeleteAll.disabled = true;
      await deleteAllGroupTypes();
      bsDelAll?.hide();
      showToast("success", "ลบทั้งหมดสำเร็จ", "ลบประเภทนักศึกษาทั้งหมดแล้ว");
      await refresh();
    } catch (e2) {
      showToast("danger", "ลบทั้งหมดไม่สำเร็จ", e2.message || "เกิดข้อผิดพลาดในการลบทั้งหมด");
    } finally {
      btnConfirmDeleteAll.disabled = false;
    }
  });

  // ยืนยันลบเดี่ยว
  btnConfirmDelete?.addEventListener("click", async () => {
    if (!pendingDeleteId) return;
    try {
      btnConfirmDelete.disabled = true;
      await deleteGroupType(pendingDeleteId);
      bsDel?.hide();
      showToast("success", "ลบสำเร็จ", "รายการถูกลบแล้ว");
      pendingDeleteId = null;
      await refresh();
    } catch (err) {
      showToast("danger", "ลบไม่สำเร็จ", err.message || "เกิดข้อผิดพลาดในการลบ");
    } finally {
      btnConfirmDelete.disabled = false;
    }
  });
});
