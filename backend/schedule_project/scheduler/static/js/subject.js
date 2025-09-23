// subject.js — ทำงานคล้ายหน้า teacher: CRUD + Modal edit + refresh ทันที
document.addEventListener("DOMContentLoaded", () => {
  // ---------- Config ----------
  // ใช้ REST เดิมของคุณ:
  // GET/POST/DELETE (ทั้งหมด) : /api/subjects/
  // GET/PUT/DELETE (รายตัว)     : /api/subjects/<id>/
  const API_BASE = "/api/subjects/";

  // ---------- Elements ----------
  const form = document.getElementById("subjectForm");
  const codeInput = document.getElementById("subject_code");
  const nameInput = document.getElementById("subject_name");
  const tbody = document.getElementById("subjectTableBody");
  const btnCancel = document.getElementById("btnCancelSubjectEdit");
  const btnSubmit = document.getElementById("btnAddSubject");
  const btnDeleteAll = document.getElementById("btnDeleteAllSubject");

  // Modal elements
  const modalEl = document.getElementById("editSubjectModal");
  const modalId = document.getElementById("edit_subject_id");
  const modalCode = document.getElementById("edit_subject_code");
  const modalName = document.getElementById("edit_subject_name");

  let editingId = null;

  // ---------- Helpers ----------
  const getCSRFToken = () => {
    const el = form?.querySelector('input[name="csrfmiddlewaretoken"]');
    return el ? el.value : "";
  };

  const jsonHeaders = () => ({
    "Content-Type": "application/json",
    "X-CSRFToken": getCSRFToken(),
    Accept: "application/json",
  });

  const setLoading = (isLoading) => {
    if (!btnSubmit) return;
    btnSubmit.disabled = isLoading;
    btnSubmit.querySelector("span")?.classList?.toggle("d-none", isLoading);
    let spinner = btnSubmit.querySelector(".spinner-border");
    if (isLoading) {
      if (!spinner) {
        spinner = document.createElement("span");
        spinner.className = "spinner-border spinner-border-sm ms-2";
        spinner.setAttribute("role", "status");
        spinner.setAttribute("aria-hidden", "true");
        btnSubmit.appendChild(spinner);
      }
    } else if (spinner) {
      spinner.remove();
    }
  };

  const escapeHtml = (s) =>
    String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");

  const parseJSONSafe = async (res) => {
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) return res.json();
    const text = await res.text();
    return { status: "error", message: text || `HTTP ${res.status}` };
  };

  const handleAPIError = async (res, fallback) => {
    const data = await parseJSONSafe(res);
    const msg =
      data?.message ||
      data?.detail ||
      data?.error ||
      fallback ||
      `HTTP ${res.status}`;
    throw new Error(msg);
  };

  // ---------- CRUD ----------
  const listSubjects = async () => {
    const res = await fetch(API_BASE, {
      headers: { Accept: "application/json" },
    });
    if (!res.ok) await handleAPIError(res, "โหลดข้อมูลไม่สำเร็จ");
    // สมมติ API collection คืน array ของวิชา: [{id, code, name}, ...]
    // ถ้าใช้ DRF viewset/serializer อาจเป็น {results: [...]} ให้ปรับตรงนี้
    return res.json();
  };

  const createSubject = async ({ code, name }) => {
    const res = await fetch(API_BASE, {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify({ code, name }),
    });
    if (!res.ok) await handleAPIError(res, "เพิ่มข้อมูลไม่สำเร็จ");
    return res.json();
  };

  const updateSubject = async (id, { code, name }) => {
    const res = await fetch(`${API_BASE}${id}/`, {
      method: "PUT",
      headers: jsonHeaders(),
      body: JSON.stringify({ code, name }),
    });
    if (!res.ok) await handleAPIError(res, "แก้ไขข้อมูลไม่สำเร็จ");
    return res.json();
  };

  const deleteSubject = async (id) => {
    const res = await fetch(`${API_BASE}${id}/`, {
      method: "DELETE",
      headers: { "X-CSRFToken": getCSRFToken(), Accept: "application/json" },
    });
    if (!res.ok) await handleAPIError(res, "ลบข้อมูลไม่สำเร็จ");
    return true;
  };

  const deleteAllSubjects = async () => {
    // สมมติให้ DELETE ที่ collection = ลบทั้งหมด (ตามไฟล์เดิม)
    const res = await fetch(API_BASE, {
      method: "DELETE",
      headers: { "X-CSRFToken": getCSRFToken(), Accept: "application/json" },
    });
    if (!res.ok) await handleAPIError(res, "ลบทั้งหมดไม่สำเร็จ");
    return true;
  };

  // ---------- Render ----------
  // ใส่ข้อความในปุ่มให้เหมือนหน้า teacher
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
          <i class="bi bi-pencil-square me-1"></i><span>แก้ไข</span>
        </button>
        <button type="button" class="btn-danger-gradient btn-delete" title="ลบ">
          <i class="bi bi-trash3 me-1"></i><span>ลบ</span>
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

  const refresh = async () => {
    try {
      const data = await listSubjects();
      // ถ้า API เป็น {results:[...]} ให้ใช้ data.results
      const items = Array.isArray(data) ? data : data.results || [];
      renderTable(items);
    } catch (err) {
      alert(err.message || "เกิดข้อผิดพลาดในการโหลดข้อมูล");
    }
  };

  // ---------- Events ----------
  refresh();

  // เพิ่มข้อมูล ด้วยฟอร์มด้านบน
  form?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const code = codeInput.value.trim();
    const name = nameInput.value.trim();
    if (!code || !name) {
      alert('กรุณากรอก "รหัสวิชา" และ "ชื่อรายวิชา" ให้ครบ');
      return;
    }
    try {
      setLoading(true);
      await createSubject({ code, name });
      form.reset();
      await refresh();
    } catch (err) {
      alert(err.message || "เกิดข้อผิดพลาดในการบันทึก");
    } finally {
      setLoading(false);
    }
  });

  // ยกเลิกโหมดแก้ (สำหรับกรณีคุณอยากใช้ฟอร์มด้านบนแก้ด้วย)
  btnCancel?.addEventListener("click", () => {
    form.reset();
    editingId = null;
    btnCancel.classList.add("d-none");
    btnSubmit.innerHTML = `<i class="bi bi-plus-lg me-2"></i><span>เพิ่มข้อมูล</span>`;
  });

  // ตาราง: แก้ไข/ลบ
  tbody?.addEventListener("click", async (e) => {
    const editBtn = e.target.closest(".btn-edit");
    const delBtn = e.target.closest(".btn-delete");
    const row = e.target.closest("tr");
    const id = row?.dataset?.id;

    if (editBtn) {
      const code =
        editBtn.dataset.code ||
        row.querySelector("td:nth-child(1)")?.textContent.trim() ||
        "";
      const name =
        editBtn.dataset.name ||
        row.querySelector("td:nth-child(2)")?.textContent.trim() ||
        "";

      modalId.value = id || "";
      modalCode.value = code;
      modalName.value = name;

      new bootstrap.Modal(modalEl).show();
      return;
    }

    if (delBtn) {
      if (!id) return;
      if (!confirm("ยืนยันลบรายวิชานี้?")) return;
      try {
        await deleteSubject(id);
        await refresh();
      } catch (err) {
        alert(err.message || "เกิดข้อผิดพลาดในการลบ");
      }
    }
  });

  // ลบทั้งหมด
  btnDeleteAll?.addEventListener("click", async () => {
    if (!confirm("ยืนยันลบรายวิชาทั้งหมด? การกระทำนี้ย้อนกลับไม่ได้")) return;
    try {
      btnDeleteAll.disabled = true;
      await deleteAllSubjects();
      await refresh();
    } catch (err) {
      alert(err.message || "เกิดข้อผิดพลาดในการลบทั้งหมด");
    } finally {
      btnDeleteAll.disabled = false;
    }
  });

  // บันทึกใน Modal (PUT)
  document
    .getElementById("btnSaveSubject")
    ?.addEventListener("click", async () => {
      const id = modalId.value;
      const code = modalCode.value.trim();
      const name = modalName.value.trim();

      if (!id) {
        alert("ไม่พบรหัสรายการ");
        return;
      }
      if (!code || !name) {
        alert('กรุณากรอก "รหัสวิชา" และ "ชื่อรายวิชา" ให้ครบ');
        return;
      }

      try {
        await updateSubject(id, { code, name });
        await refresh();
        bootstrap.Modal.getInstance(modalEl).hide();
      } catch (err) {
        // กรณีซ้ำ/ผิดพลาด backend ส่ง JSON message มา → alert ข้อความนั้น
        alert(err.message || "ไม่สามารถบันทึกได้");
      }
    });
});
