// /static/js/subject.js
document.addEventListener("DOMContentLoaded", () => {
  const API_BASE = "/api/subjects/";

  // ---- Elements ----
  const form = document.getElementById("subjectForm");
  const codeInput = document.getElementById("subject_code");
  const nameInput = document.getElementById("subject_name");
  const tbody = document.getElementById("subjectTableBody");
  const btnSubmit = document.getElementById("btnAddSubject");
  const btnDeleteAll = document.getElementById("btnDeleteAllSubject");

  // Edit modal
  const modalEl = document.getElementById("editSubjectModal");
  const bsEdit = modalEl ? new bootstrap.Modal(modalEl) : null;
  const modalId = document.getElementById("edit_subject_id");
  const modalCode = document.getElementById("edit_subject_code");
  const modalName = document.getElementById("edit_subject_name");
  const btnSave = document.getElementById("btnSaveSubject");

  // Confirm delete (single) modal  ⬅️ ใหม่ (แทน confirm())
  const delModalEl = document.getElementById("confirmDeleteModal");
  const bsDel = delModalEl ? new bootstrap.Modal(delModalEl) : null;
  const delItemCode = document.getElementById("del_item_code");
  const delItemName = document.getElementById("del_item_name");
  const btnConfirmDelete = document.getElementById("btnConfirmDelete");
  let pendingDeleteId = null;

  // Confirm delete-all modal
  const delAllModalEl = document.getElementById("confirmDeleteAllModal");
  const bsDelAll = delAllModalEl ? new bootstrap.Modal(delAllModalEl) : null;
  const btnConfirmDeleteAll = document.getElementById("btnConfirmDeleteAll");

  // Toast host
  const toastHost = document.getElementById("toastHost");

  // ---- Helpers ----
  const getCSRF = () => {
    const el = form?.querySelector('input[name="csrfmiddlewaretoken"]');
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
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");

  const setLoading = (btn, loading) => {
    if (!btn) return;
    btn.disabled = loading;
    const span = btn.querySelector("span");
    if (span) span.classList.toggle("d-none", loading);
    let spinner = btn.querySelector(".spinner-border");
    if (loading && !spinner) {
      spinner = document.createElement("span");
      spinner.className = "spinner-border spinner-border-sm ms-2";
      spinner.setAttribute("role", "status");
      spinner.setAttribute("aria-hidden", "true");
      btn.appendChild(spinner);
    }
    if (!loading && spinner) spinner.remove();
  };

  // Toast (success | warning | danger | info)
  function showToast(kind, title, message) {
    if (!toastHost) return alert(message || title || "");
    const bgMap = {
      success: "bg-success text-white",
      warning: "bg-warning",
      danger: "bg-danger text-white",
      info: "bg-primary text-white",
    };
    const headerClass = bgMap[kind] || "bg-dark text-white";
    const id = `t${Date.now()}`;
    const el = document.createElement("div");
    el.className = "toast align-items-center border-0 shadow overflow-hidden";
    el.style.borderRadius = "12px";
    el.id = id;
    el.setAttribute("role", "alert");
    el.setAttribute("aria-live", "assertive");
    el.setAttribute("aria-atomic", "true");
    el.innerHTML = `
      <div class="toast-header ${headerClass}">
        <strong class="me-auto">${escapeHtml(title || "")}</strong>
        <button type="button" class="btn-close btn-close-white ms-2 mb-1" data-bs-dismiss="toast" aria-label="Close"></button>
      </div>
      <div class="toast-body">${escapeHtml(message || "")}</div>`;
    toastHost.appendChild(el);
    const t = new bootstrap.Toast(el, { delay: 3500, autohide: true });
    t.show();
  }

  // ---- API ----
  const listSubjects = async () => {
    const res = await fetch(`/api/subjects/?order=-id`, { headers: { Accept: "application/json" } });
    await ensureOk(res, "โหลดข้อมูลไม่สำเร็จ");
    const data = await res.json();
    return Array.isArray(data) ? data : data.results || [];
  };

  const createSubject = async ({ code, name }) => {
    const res = await fetch(API_BASE, {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify({ code, name }),
    });
    await ensureOk(res, "เพิ่มข้อมูลไม่สำเร็จ");
    return res.json();
  };

  const updateSubject = async (id, { code, name }) => {
    const res = await fetch(`${API_BASE}${id}/`, {
      method: "PUT",
      headers: jsonHeaders(),
      body: JSON.stringify({ code, name }),
    });
    await ensureOk(res, "แก้ไขข้อมูลไม่สำเร็จ");
    return res.json();
  };

  const deleteSubject = async (id) => {
    const res = await fetch(`${API_BASE}${id}/`, {
      method: "DELETE",
      headers: { "X-CSRFToken": getCSRF(), Accept: "application/json" },
    });
    await ensureOk(res, "ลบข้อมูลไม่สำเร็จ");
    return true;
  };

  const deleteAllSubjects = async () => {
    const res = await fetch(`/api/subjects/delete-all/`, {
      method: "DELETE",
      headers: { "X-CSRFToken": getCSRF(), Accept: "application/json" },
    });
    await ensureOk(res, "ลบทั้งหมดไม่สำเร็จ");
    return true;
  };

  // ---- Render ----
  const rowHTML = ({ id, code, name }) => `
    <tr data-id="${id}">
      <td class="fw-semibold text-center">${escapeHtml(code)}</td>
      <td>${escapeHtml(name)}</td>
      <td class="d-flex justify-content-center gap-2">
        <button type="button" class="btn-warning-gradient btn-edit"
                data-id="${id}"
                data-code="${escapeHtml(code)}"
                data-name="${escapeHtml(name)}"
                title="แก้ไข">
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
          <td colspan="3" class="text-center text-muted">ไม่มีข้อมูลรายวิชา</td>
        </tr>`;
      return;
    }
    tbody.innerHTML = items.map(rowHTML).join("");
  };

  // cache ไว้กันซ้ำและใช้เรนเดอร์เร็ว
  let subjectCache = [];
  const refresh = async () => {
    try {
      subjectCache = await listSubjects();
      renderTable(subjectCache);
    } catch (e) {
      showToast("danger", "โหลดข้อมูลล้มเหลว", e.message || "เกิดข้อผิดพลาดในการโหลดข้อมูล");
    }
  };

  // ---- Init ----
  refresh();

  // ---- Events ----
  // เพิ่มข้อมูล
  form?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const code = codeInput.value.trim().toUpperCase();
    const name = nameInput.value.trim();
    if (!code || !name) {
      showToast("warning", "ข้อมูลไม่ครบ", 'กรุณากรอก "รหัสวิชา" และ "ชื่อรายวิชา" ให้ครบ');
      return;
    }
    // กันซ้ำฝั่ง client
    const dup = subjectCache.find((x) => (x.code || "").toUpperCase() === code);
    if (dup) {
      showToast("warning", "รหัสวิชาซ้ำ", `รหัสวิชา ${code} มีอยู่แล้ว`);
      return;
    }
    try {
      setLoading(btnSubmit, true);
      await createSubject({ code, name });
      form.reset();
      showToast("success", "เพิ่มสำเร็จ", `เพิ่มรายวิชา ${code} แล้ว`);
      await refresh();
    } catch (e2) {
      showToast("warning", "เพิ่มไม่สำเร็จ", e2.message || "เกิดข้อผิดพลาดในการบันทึก");
    } finally {
      setLoading(btnSubmit, false);
    }
  });

  // แก้ไข/ลบ รายตัว
  tbody?.addEventListener("click", async (e) => {
    const row = e.target.closest("tr");
    if (!row) return;
    const id = row.dataset.id;

    // แก้ไข
    const editBtn = e.target.closest(".btn-edit");
    if (editBtn && bsEdit) {
      modalId.value = id;
      modalCode.value = editBtn.dataset.code || row.children[0].textContent.trim();
      modalName.value = editBtn.dataset.name || row.children[1].textContent.trim();
      bsEdit.show();
      return;
    }

    // ลบ (รายตัว) → เปิด modal สวยๆ (แทน confirm())
    const delBtn = e.target.closest(".btn-delete");
    if (delBtn && id && bsDel) {
      pendingDeleteId = id;
      delItemCode.textContent = row.children[0]?.textContent.trim() || "";
      delItemName.textContent = row.children[1]?.textContent.trim() || "";
      bsDel.show();
      return;
    }
  });

  // บันทึกแก้ไข
  btnSave?.addEventListener("click", async () => {
    const id = modalId.value;
    const code = modalCode.value.trim().toUpperCase();
    const name = modalName.value.trim();
    if (!code || !name) {
      showToast("warning", "ข้อมูลไม่ครบ", 'กรุณากรอก "รหัสวิชา" และ "ชื่อรายวิชา" ให้ครบ');
      return;
    }
    const dup = subjectCache.find(
      (x) => String(x.id) !== String(id) && (x.code || "").toUpperCase() === code
    );
    if (dup) {
      showToast("warning", "รหัสวิชาซ้ำ", `รหัสวิชา ${code} ซ้ำกับรายการเดิม`);
      return;
    }
    try {
      btnSave.disabled = true;
      await updateSubject(id, { code, name });
      bsEdit?.hide();
      showToast("success", "แก้ไขสำเร็จ", `บันทึกรายวิชา ${code} แล้ว`);
      await refresh();
    } catch (e2) {
      showToast("warning", "แก้ไขไม่สำเร็จ", e2.message || "เกิดข้อผิดพลาดในการแก้ไข");
    } finally {
      btnSave.disabled = false;
    }
  });

  // ยืนยันลบ "รายตัว" จาก modal
  btnConfirmDelete?.addEventListener("click", async () => {
    if (!pendingDeleteId) return;
    try {
      btnConfirmDelete.disabled = true;
      await deleteSubject(pendingDeleteId);
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

  // ลบทั้งหมด (ยืนยันผ่าน modal)
  btnDeleteAll?.addEventListener("click", () => {
    bsDelAll?.show();
  });

  btnConfirmDeleteAll?.addEventListener("click", async () => {
    try {
      btnConfirmDeleteAll.disabled = true;
      await deleteAllSubjects();
      bsDelAll?.hide();
      showToast("success", "ลบทั้งหมดสำเร็จ", "ลบข้อมูลรายวิชาทั้งหมดแล้ว");
      await refresh();
    } catch (e2) {
      showToast("danger", "ลบทั้งหมดไม่สำเร็จ", e2.message || "เกิดข้อผิดพลาดในการลบทั้งหมด");
    } finally {
      btnConfirmDeleteAll.disabled = false;
    }
  });
});
