// /static/js/teacher.js
document.addEventListener("DOMContentLoaded", () => {
  // ---- CSRF + fetch helpers ----
  const csrftoken = (() => {
    const m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  })();

  async function apiGet(url) {
    const r = await fetch(url);
    const j = await r.json();
    if (!r.ok || j.status !== "success")
      throw new Error(j.message || `HTTP ${r.status}`);
    return j;
  }
  async function apiPost(url, payload) {
    const r = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrftoken },
      body: JSON.stringify(payload),
    });
    const j = await r.json();
    if (!r.ok || j.status !== "success")
      throw new Error(j.message || `HTTP ${r.status}`);
    return j;
  }
  async function apiDelete(url) {
    const r = await fetch(url, {
      method: "DELETE",
      headers: { "X-CSRFToken": csrftoken },
    });
    const j = await r.json();
    if (!r.ok || j.status !== "success")
      throw new Error(j.message || `HTTP ${r.status}`);
    return j;
  }

  // --- Controller สำหรับ Teacher ---
  window.teacherController = makeController({
    key: "teacher",
    formId: "teacherForm",
    fields: [
      // เอา teacher_id ออก ให้เหลือแค่ชื่ออาจารย์
      { id: "teacher_name", key: "name", label: "ชื่ออาจารย์", required: true },
    ],
    tableBodyId: "teacherTableBody",
    addBtnId: "btnAddTeacher",
    cancelBtnId: "btnCancelTeacherEdit",
    deleteAllBtnId: "btnDeleteAllTeacher",

    remote: {
      async load() {
        // คาดว่า backend คืน items: [{id, name}, ...]
        const { items } = await apiGet("/api/teacher/list/");
        return items;
      },
      async create(values) {
        // ส่งเฉพาะ name เท่านั้น
        const payload = {
          name: String(values.name || "").trim(),
        };
        await apiPost("/api/teacher/add/", payload);
      },
      async remove(id) {
        // ลบตาม PK จริงของตาราง Teacher
        await apiDelete(`/api/teacher/delete/${id}/`);
      },
      async removeAll() {
        await apiDelete("/api/teacher/delete-all/");
      },
    },
  });

  // ---- Edit Modal ----
  window.editTeacher = async function (btn) {
    const ev = window.event;
    if (ev) {
      try {
        ev.preventDefault();
      } catch {}
      try {
        ev.stopPropagation();
      } catch {}
      if (ev.stopImmediatePropagation) ev.stopImmediatePropagation();
    }

    // 1) พยายามอ่าน id จากปุ่มก่อน แล้วค่อยจาก <tr>
    const idFromBtn = btn?.dataset?.id;
    const tr = btn.closest("tr");
    const idFromTr = tr ? tr.getAttribute("data-id") : null;
    let id = idFromBtn || idFromTr;

    // 2) อ่านชื่อจาก data-name หรือคอลัมน์แรก
    let name =
      btn?.dataset?.name ||
      tr?.querySelector("td:first-child")?.textContent?.trim() ||
      "";

    // 3) Fallback: ถ้า id ยังไม่มี ให้ค้นจาก /api/teacher/list/ ด้วยชื่อ (กันกรณี makeController สร้างแถวโดยไม่มี data-id)
    if (!id && name) {
      try {
        const { items } = await apiGet("/api/teacher/list/");
        const found = items.find(
          (x) => (x.name || "").trim().toLowerCase() === name.toLowerCase()
        );
        if (found) id = String(found.id);
      } catch (e) {
        console.warn("fallback lookup failed:", e);
      }
    }

    if (!id) {
      console.error("ไม่พบ id สำหรับการแก้ไข", {
        idFromBtn,
        idFromTr,
        tr,
        btn,
        name,
      });
      alert("ไม่พบรหัสรายการที่จะใช้แก้ไข");
      return;
    }

    document.getElementById("edit_teacher_id").value = id;
    document.getElementById("edit_teacher_name").value = name;

    new bootstrap.Modal(document.getElementById("editTeacherModal")).show();
  };

  // ✅ ดักคลิกปุ่มแก้ไขก่อน makeController (capture)
  const tbody = document.getElementById("teacherTableBody");
  if (tbody) {
    tbody.addEventListener(
      "click",
      (e) => {
        const editBtn = e.target.closest(".btn-edit, .btn-warning-gradient");
        if (editBtn) {
          e.preventDefault();
          e.stopPropagation();
          if (e.stopImmediatePropagation) e.stopImmediatePropagation();
          editTeacher(editBtn);
        }
      },
      true
    );
  }

  // ====== Renderer แถวแบบมีไอคอน ======
  const teacherTbody = document.getElementById("teacherTableBody");

  const teacherRowHTML = ({ id, name }) => `
    <tr data-id="${id}">
      <td>${name}</td>
      <td class="d-flex justify-content-center gap-2">
        <button type="button" class="btn-warning-gradient btn-edit"
                data-id="${id}" data-name="${name}"
                onclick="editTeacher(this)" title="แก้ไข">
          <i class="bi bi-pencil-square me-1"></i><span>แก้ไข</span>
        </button>
        <button type="button" class="btn-danger-gradient"
                onclick="deleteTeacher(this)" title="ลบ">
          <i class="bi bi-trash3 me-1"></i><span>ลบ</span>
        </button>
      </td>
    </tr>
  `;

  function renderTeacherRows(items) {
    if (!teacherTbody) return;
    if (!Array.isArray(items) || items.length === 0) {
      teacherTbody.innerHTML = `
      <tr class="empty-row">
        <td colspan="2" class="text-center text-muted">ไม่มีข้อมูลอาจารย์ผู้สอน</td>
      </tr>`;
      return;
    }
    teacherTbody.innerHTML = items.map(teacherRowHTML).join("");
  }

  // ให้ reload() ของ controller ใช้ renderer นี้แทนของเดิม
  if (window.teacherController) {
    const _load = window.teacherController.remote.load;
    window.teacherController.reload = async function () {
      const items = await _load();
      renderTeacherRows(items);
    };
    // เรียกครั้งแรกให้แสดงแถวที่มีไอคอน
    window.teacherController.reload();
  }

  // กด "บันทึก" ใน modal
  document
    .getElementById("btnSaveTeacher")
    .addEventListener("click", async () => {
      const id = document.getElementById("edit_teacher_id").value;
      const name = document.getElementById("edit_teacher_name").value.trim();

      if (!id) {
        alert("ไม่พบรหัสรายการ");
        return;
      }
      if (!name) {
        alert("กรุณากรอกชื่ออาจารย์");
        return;
      }

      try {
        const r = await fetch(`/api/teacher/update/${id}/`, {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": csrftoken,
          },
          body: JSON.stringify({ name }),
        });

        const j = await r.json();
        if (!r.ok || j.status !== "success")
          throw new Error(j.message || `HTTP ${r.status}`);

        // 👉 refresh ตารางใหม่จาก server
        if (window.teacherController) {
          await window.teacherController.reload();
        }

        bootstrap.Modal.getInstance(
          document.getElementById("editTeacherModal")
        ).hide();
      } catch (err) {
        alert(err.message || "เกิดข้อผิดพลาดในการบันทึก");
      }
    });
});
