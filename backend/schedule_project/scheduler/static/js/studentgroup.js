// /static/js/studentgroup.js
document.addEventListener("DOMContentLoaded", () => {
  // ===== API (ให้ list เรียงใหม่อยู่บนสุด) =====
  const API = {
    list:  "/api/studentgroup/list/?order=-id",
    add:   "/api/studentgroup/add/",                       // POST {name, type}
    update:(id) => `/api/studentgroup/update/${id}/`,      // PUT  {name, type}
    del:   (id) => `/api/studentgroup/delete/${id}/`,      // DELETE
    delAll:"/api/studentgroup/delete-all/",                // DELETE
    gtypes:"/api/grouptype/list/?order=-id",               // GET   {items:[{id,type}]}
  };

  // ===== Elements =====
  const form = document.getElementById("studentGroupForm");
  const nameInput = document.getElementById("group_name");
  const typeSelect = document.getElementById("group_type");
  const tbody = document.getElementById("studentGroupTableBody");
  const btnSubmit = document.getElementById("btnAddStudentGroup");
  const btnCancel = document.getElementById("btnCancelStudentGroupEdit");
  const btnDeleteAll = document.getElementById("btnDeleteAllStudentGroup");
  const toastHost = document.getElementById("toastHost");

  // Edit modal
  const editEl = document.getElementById("editStudentGroupModal");
  const bsEdit = editEl ? new bootstrap.Modal(editEl) : null;
  const editId = document.getElementById("edit_sg_id");
  const editName = document.getElementById("edit_sg_name");
  const editType = document.getElementById("edit_sg_type");
  const btnSave = document.getElementById("btnSaveStudentGroup");

  // Delete single modal
  const delModalEl = document.getElementById("confirmDeleteModal");
  const bsDel = delModalEl ? new bootstrap.Modal(delModalEl) : null;
  const delItemName = document.getElementById("del_item_name");
  const btnConfirmDelete = document.getElementById("btnConfirmDelete");
  let pendingDeleteId = null;

  // Delete all modal
  const delAllModalEl = document.getElementById("confirmDeleteAllModal");
  const bsDelAll = delAllModalEl ? new bootstrap.Modal(delAllModalEl) : null;
  const btnConfirmDeleteAll = document.getElementById("btnConfirmDeleteAll");

  // ===== Helpers =====
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
    if (res.ok) return res.json();
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
      sp.setAttribute("role", "status");
      sp.setAttribute("aria-hidden", "true");
      btn.appendChild(sp);
    }
    if (!on && sp) sp.remove();
  };
  const showToast = (kind, title, message) => {
    if (!toastHost) return alert(message || title || "");
    const cls = {
      success: "bg-success text-white",
      warning: "bg-warning",
      danger:  "bg-danger text-white",
      info:    "bg-primary text-white",
    }[kind] || "bg-dark text-white";
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

  // ===== API wrappers =====
  const listGroupTypes = async () => {
    const res = await fetch(API.gtypes, { headers: { Accept: "application/json" } });
    const data = await ensureOk(res, "โหลดประเภทนักศึกษาไม่สำเร็จ");
    return Array.isArray(data?.items) ? data.items : [];
  };
  const listStudentGroups = async () => {
    const res = await fetch(API.list, { headers: { Accept: "application/json" } });
    const data = await ensureOk(res, "โหลดกลุ่มนักศึกษาไม่สำเร็จ");
    return Array.isArray(data?.items) ? data.items : [];
  };
  const createStudentGroup = async ({ name, type }) => {
    const res = await fetch(API.add, {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify({ name, type }), // ไม่ส่ง id
    });
    return ensureOk(res, "เพิ่มข้อมูลไม่สำเร็จ");
  };
  const updateStudentGroup = async (id, { name, type }) => {
    const res = await fetch(API.update(id), {
      method: "PUT",
      headers: jsonHeaders(),
      body: JSON.stringify({ name, type }),
    });
    return ensureOk(res, "แก้ไขข้อมูลไม่สำเร็จ");
  };
  const deleteStudentGroup = async (id) => {
    const res = await fetch(API.del(id), {
      method: "DELETE",
      headers: { "X-CSRFToken": getCSRF(), Accept: "application/json" },
    });
    await ensureOk(res, "ลบข้อมูลไม่สำเร็จ");
  };
  const deleteAllStudentGroups = async () => {
    const res = await fetch(API.delAll, {
      method: "DELETE",
      headers: { "X-CSRFToken": getCSRF(), Accept: "application/json" },
    });
    await ensureOk(res, "ลบทั้งหมดไม่สำเร็จ");
  };

  // ===== Render =====
  const rowHTML = ({ id, name, type_name }) => `
    <tr data-id="${id}">
      <td>${escapeHtml(name)}</td>
      <td>${escapeHtml(type_name || "")}</td>
      <td class="d-flex justify-content-center gap-2">
        <button type="button" class="btn-warning-gradient btn-edit" title="แก้ไข"><span>แก้ไข</span></button>
        <button type="button" class="btn-danger-gradient btn-delete" title="ลบ"><span>ลบ</span></button>
      </td>
    </tr>`;
  const renderTable = (items) => {
    if (!tbody) return;
    if (!items?.length) {
      tbody.innerHTML = `<tr class="empty-row"><td colspan="3" class="text-center text-muted">ไม่มีข้อมูลกลุ่มนักศึกษา</td></tr>`;
      return;
    }
    tbody.innerHTML = items.map(rowHTML).join("");
  };

  // ===== Init / Refresh =====
  let cache = [];   // student groups
  let gtCache = []; // group types

  const refresh = async () => {
    // โหลดประเภทนักศึกษา (ทั้งฟอร์มและ modal)
    gtCache = await listGroupTypes();
    const options = `<option value="">เลือกประเภท</option>` +
      gtCache.map(g => `<option value="${g.id}">${escapeHtml(g.type)}</option>`).join("");
    if (typeSelect) typeSelect.innerHTML = options;
    if (editType)   editType.innerHTML   = options;

    // โหลดรายการกลุ่ม
    cache = await listStudentGroups();     // ได้ลำดับ -id อยู่บนสุด
    renderTable(cache);
  };
  refresh();

  // ===== Add (ห้ามชื่อซ้ำ) =====
  form?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = nameInput.value.trim();
    const type = String(typeSelect.value || "");

    if (!name) return showToast("warning","ข้อมูลไม่ครบ",'กรุณากรอก "ชื่อกลุ่มนักศึกษา"');
    if (!type) return showToast("warning","ข้อมูลไม่ครบ",'กรุณาเลือก "ประเภทนักศึกษา"');

    const norm = s => (s||"").trim().toLowerCase();
    if (cache.find(x => norm(x.name) === norm(name))) {
      return showToast("warning","ชื่อซ้ำ",`กลุ่ม "${name}" มีอยู่แล้ว`);
    }

    try {
      setLoading(btnSubmit, true);
      const res = await createStudentGroup({ name, type: Number(type) });

      // ถ้า backend คืน item -> แทรกบนสุดทันที
      const newItem = res?.item;
      if (newItem && newItem.id) {
        cache.unshift(newItem);
        renderTable(cache);
      } else {
        await refresh(); // กันเหนียว
      }

      form.reset();
      showToast("success","เพิ่มสำเร็จ",`เพิ่ม "${name}" แล้ว`);
    } catch (err) {
      showToast("danger","เพิ่มไม่สำเร็จ", err.message || "เกิดข้อผิดพลาด");
    } finally {
      setLoading(btnSubmit, false);
    }
  });

  // ===== Table actions (edit/delete) =====
  tbody?.addEventListener("click", (e) => {
    const tr = e.target.closest("tr");
    if (!tr) return;
    const id = tr.dataset.id;

    // ลบ
    if (e.target.closest(".btn-delete") && id && bsDel) {
      pendingDeleteId = id;
      delItemName.textContent = tr.children[0]?.textContent.trim() || "";
      bsDel.show();
      return;
    }

    // แก้ไข
    if (e.target.closest(".btn-edit") && bsEdit) {
      const row = cache.find(x => String(x.id) === String(id));
      if (!row) return;
      editId.value = row.id;
      editName.value = row.name;
      // map type id จากแคช (รองรับกรณี backend ส่งทั้ง type / type_name)
      const gtId = row.type ?? gtCache.find(g => g.type === row.type_name)?.id ?? "";
      editType.value = gtId ? String(gtId) : "";
      bsEdit.show();
    }
  });

  // ===== Save edit =====
  btnSave?.addEventListener("click", async () => {
    const id = editId.value;
    const name = editName.value.trim();
    const type = String(editType.value || "");

    if (!name) return showToast("warning","ข้อมูลไม่ครบ",'กรุณากรอก "ชื่อกลุ่มนักศึกษา"');
    if (!type) return showToast("warning","ข้อมูลไม่ครบ",'กรุณาเลือก "ประเภทนักศึกษา"');

    const norm = s => (s||"").trim().toLowerCase();
    if (cache.find(x => String(x.id)!==String(id) && norm(x.name)===norm(name))) {
      return showToast("warning","ชื่อซ้ำ",`"${name}" ซ้ำกับรายการเดิม`);
    }

    try {
      btnSave.disabled = true;
      await updateStudentGroup(id, { name, type: Number(type) });
      bsEdit?.hide();
      showToast("success","แก้ไขสำเร็จ",`บันทึก "${name}" แล้ว`);
      await refresh();
    } catch (err) {
      showToast("danger","แก้ไขไม่สำเร็จ", err.message || "เกิดข้อผิดพลาด");
    } finally {
      btnSave.disabled = false;
    }
  });

  // ===== Delete all =====
  btnDeleteAll?.addEventListener("click", () => bsDelAll?.show());
  btnConfirmDeleteAll?.addEventListener("click", async () => {
    try {
      btnConfirmDeleteAll.disabled = true;
      await deleteAllStudentGroups();
      bsDelAll?.hide();
      showToast("success","ลบทั้งหมดสำเร็จ","ลบกลุ่มนักศึกษาทั้งหมดแล้ว");
      await refresh();
    } catch (err) {
      showToast("danger","ลบทั้งหมดไม่สำเร็จ", err.message || "เกิดข้อผิดพลาด");
    } finally {
      btnConfirmDeleteAll.disabled = false;
    }
  });

  // ===== Delete single =====
  btnConfirmDelete?.addEventListener("click", async () => {
    if (!pendingDeleteId) return;
    try {
      btnConfirmDelete.disabled = true;
      await deleteStudentGroup(pendingDeleteId);
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

  // ปุ่มยกเลิก (กันเผื่ออนาคตมีโหมดแก้ไขในแถว)
  btnCancel?.addEventListener("click", () => {
    form.reset();
    btnCancel.classList.add("d-none");
    btnSubmit.innerHTML = '<i class="bi bi-plus-lg me-2"></i><span>เพิ่มข้อมูล</span>';
  });
});
