// /static/js/teacher.js
document.addEventListener("DOMContentLoaded", () => {
  const API = {
    LIST:  "/api/teacher/list/",
    ADD:   "/api/teacher/add/",
    DEL:   (id) => `/api/teacher/delete/${id}/`,
    DEL_ALL: "/api/teacher/delete-all/",
    UPDATE: (id) => `/api/teacher/update/${id}/`,
  };

  // ===== Elements =====
  const form = document.getElementById("teacherForm");
  const nameInput = document.getElementById("teacher_name");
  const tbody = document.getElementById("teacherTableBody");
  const btnAdd = document.getElementById("btnAddTeacher");
  const btnDeleteAll = document.getElementById("btnDeleteAllTeacher");

  // edit modal
  const editModalEl = document.getElementById("editTeacherModal");
  const bsEdit = editModalEl ? new bootstrap.Modal(editModalEl) : null;
  const editId = document.getElementById("edit_teacher_id");
  const editName = document.getElementById("edit_teacher_name");
  const btnSave = document.getElementById("btnSaveTeacher");

  // confirm delete single
  const delModalEl = document.getElementById("confirmDeleteTeacherModal");
  const bsDel = delModalEl ? new bootstrap.Modal(delModalEl) : null;
  const delTeacherName = document.getElementById("del_teacher_name");
  const btnConfirmDelete = document.getElementById("btnConfirmDeleteTeacher");
  let pendingDeleteId = null;

  // confirm delete all
  const delAllModalEl = document.getElementById("confirmDeleteAllTeacherModal");
  const bsDelAll = delAllModalEl ? new bootstrap.Modal(delAllModalEl) : null;
  const btnConfirmDeleteAll = document.getElementById("btnConfirmDeleteAllTeacher");

  // toast
  const toastHost = document.getElementById("toastHost");

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
  const ensureOk = async (res, fb) => {
    if (res.ok) return;
    let msg = fb;
    try { const j = await res.json(); msg = j.message || j.detail || fb; } catch {}
    throw new Error(msg || `HTTP ${res.status}`);
  };
  const escape = (s) =>
    String(s ?? "")
      .replace(/&/g,"&amp;").replace(/</g,"&lt;")
      .replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#039;");

  function showToast(kind, title, message) {
    if (!toastHost) return alert(message || title || "");
    const bg = { success:"bg-success text-white", warning:"bg-warning", danger:"bg-danger text-white", info:"bg-primary text-white" }[kind] || "bg-dark text-white";
    const el = document.createElement("div");
    el.className = "toast align-items-center border-0 shadow overflow-hidden";
    el.style.borderRadius = "12px";
    el.innerHTML = `
      <div class="toast-header ${bg}">
        <strong class="me-auto">${escape(title || "")}</strong>
        <button type="button" class="btn-close btn-close-white ms-2 mb-1" data-bs-dismiss="toast" aria-label="Close"></button>
      </div>
      <div class="toast-body">${escape(message || "")}</div>`;
    toastHost.appendChild(el);
    new bootstrap.Toast(el, { delay: 3500, autohide: true }).show();
  }

  // ===== API =====
  const listTeachers = async () => {
    const r = await fetch("/api/teacher/list/?order=-id", { headers: { Accept: "application/json" }});
    if (!r.ok) throw new Error("โหลดข้อมูลไม่สำเร็จ");
    const j = await r.json();
    const items = j.items || j.results || j || [];
    // บังคับเรียงใหม่: ล่าสุดอยู่บน
    items.sort((a, b) => Number(b.id) - Number(a.id));
    return items;
  };
  const addTeacher = async ({ name }) => {
    const r = await fetch(API.ADD, { method:"POST", headers: jsonHeaders(), body: JSON.stringify({ name }) });
    await ensureOk(r, "เพิ่มข้อมูลไม่สำเร็จ");
    return r.json();
  };
  const updateTeacher = async (id, { name }) => {
    const r = await fetch(API.UPDATE(id), { method:"PUT", headers: jsonHeaders(), body: JSON.stringify({ name }) });
    await ensureOk(r, "แก้ไขข้อมูลไม่สำเร็จ");
    return r.json();
  };
  const deleteTeacher = async (id) => {
    const r = await fetch(API.DEL(id), { method:"DELETE", headers: { "X-CSRFToken": getCSRF(), Accept:"application/json" }});
    await ensureOk(r, "ลบข้อมูลไม่สำเร็จ");
    return true;
  };
  const deleteAll = async () => {
    const r = await fetch(API.DEL_ALL, { method:"DELETE", headers: { "X-CSRFToken": getCSRF(), Accept:"application/json" }});
    await ensureOk(r, "ลบทั้งหมดไม่สำเร็จ");
    return true;
  };

  // ===== Render =====
  const rowHTML = ({ id, name }) => `
    <tr data-id="${id}">
      <td>${escape(name)}</td>
      <td class="d-flex justify-content-center gap-2">
        <button type="button" class="btn-warning-gradient btn-edit" data-id="${id}" data-name="${escape(name)}" title="แก้ไข">
          <span>แก้ไข</span>
        </button>
        <button type="button" class="btn-danger-gradient btn-delete" title="ลบ">
          <span>ลบ</span>
        </button>
      </td>
    </tr>`;
  const render = (items) => {
    if (!Array.isArray(items) || items.length === 0) {
      tbody.innerHTML = `<tr class="empty-row"><td colspan="2" class="text-center text-muted">ไม่มีข้อมูลอาจารย์ผู้สอน</td></tr>`;
      return;
    }
    tbody.innerHTML = items.map(rowHTML).join("");
  };

  // ===== State & init =====
  let cache = [];
  const refresh = async () => { cache = await listTeachers(); render(cache); };
  refresh();

  // ===== Events =====
  // เพิ่มข้อมูล (กันชื่อซ้ำ)
  form?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = (nameInput.value || "").trim();
    if (!name) return showToast("warning","ข้อมูลไม่ครบ","กรุณากรอกชื่ออาจารย์");

    const dup = cache.find(x => (x.name || "").trim().toLowerCase() === name.toLowerCase());
    if (dup) return showToast("warning","ชื่อซ้ำ","มีชื่ออาจารย์นี้อยู่แล้ว");

    try {
      btnAdd.disabled = true;
      await addTeacher({ name });
      form.reset();
      showToast("success","เพิ่มสำเร็จ",`เพิ่มอาจารย์ ${name} แล้ว`);
      await refresh();
    } catch (err) {
      showToast("danger","เพิ่มไม่สำเร็จ", err.message || "เกิดข้อผิดพลาด");
    } finally {
      btnAdd.disabled = false;
    }
  });

  // แก้ไข/ลบ รายตัว
  tbody?.addEventListener("click", (e) => {
    const tr = e.target.closest("tr");
    if (!tr) return;
    const id = tr.dataset.id;

    // edit
    const editBtn = e.target.closest(".btn-edit");
    if (editBtn && bsEdit) {
      editId.value = id;
      editName.value = editBtn.dataset.name || tr.children[0].textContent.trim();
      bsEdit.show();
      return;
    }

    // delete (single) → modal
    const delBtn = e.target.closest(".btn-delete");
    if (delBtn && bsDel) {
      pendingDeleteId = id;
      delTeacherName.textContent = tr.children[0].textContent.trim();
      bsDel.show();
      return;
    }
  });

  // บันทึกแก้ไข (กันชื่อซ้ำ)
  btnSave?.addEventListener("click", async () => {
    const id = editId.value;
    const name = (editName.value || "").trim();
    if (!name) return showToast("warning","ข้อมูลไม่ครบ","กรุณากรอกชื่ออาจารย์");

    const dup = cache.find(x => String(x.id) !== String(id) && (x.name || "").trim().toLowerCase() === name.toLowerCase());
    if (dup) return showToast("warning","ชื่อซ้ำ","มีชื่ออาจารย์นี้อยู่แล้ว");

    try {
      btnSave.disabled = true;
      await updateTeacher(id, { name });
      bsEdit?.hide();
      showToast("success","แก้ไขสำเร็จ",`บันทึกอาจารย์ ${name} แล้ว`);
      await refresh();
    } catch (err) {
      showToast("danger","แก้ไขไม่สำเร็จ", err.message || "เกิดข้อผิดพลาด");
    } finally {
      btnSave.disabled = false;
    }
  });

  // ยืนยันลบรายตัว
  btnConfirmDelete?.addEventListener("click", async () => {
    if (!pendingDeleteId) return;
    try {
      btnConfirmDelete.disabled = true;
      await deleteTeacher(pendingDeleteId);
      bsDel?.hide();
      showToast("success","ลบสำเร็จ","ลบอาจารย์เรียบร้อย");
      pendingDeleteId = null;
      await refresh();
    } catch (err) {
      showToast("danger","ลบไม่สำเร็จ", err.message || "เกิดข้อผิดพลาด");
    } finally {
      btnConfirmDelete.disabled = false;
    }
  });

  // ลบทั้งหมด
  btnDeleteAll?.addEventListener("click", () => bsDelAll?.show());
  btnConfirmDeleteAll?.addEventListener("click", async () => {
    try {
      btnConfirmDeleteAll.disabled = true;
      await deleteAll();
      bsDelAll?.hide();
      showToast("success","ลบทั้งหมดสำเร็จ","ลบข้อมูลอาจารย์ทั้งหมดแล้ว");
      await refresh();
    } catch (err) {
      showToast("danger","ลบทั้งหมดไม่สำเร็จ", err.message || "เกิดข้อผิดพลาด");
    } finally {
      btnConfirmDeleteAll.disabled = false;
    }
  });
});
