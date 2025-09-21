// /static/js/controller.js
(function (global) {
  "use strict";

  function qs(id) { return document.getElementById(id); }

  function makeController(opts) {
    const {
      key,                    // ชื่อสั้นๆ ของหน้า เช่น 'groupallow'
      formId,                 // id ของ <form>
      fields,                 // [{id, key, label, required, requiredInvalidValue?}, ...]
      tableBodyId,            // id ของ <tbody>
      addBtnId,               // ปุ่ม เพิ่ม/บันทึก
      cancelBtnId,            // ปุ่ม ยกเลิกแก้ไข
      refreshBtnId,           // ปุ่ม รีเฟรช
      deleteAllBtnId,         // ปุ่ม ลบทั้งหมด
      remote                  // { load(), create(values), remove(id), removeAll()? }
    } = opts;

    const state = {
      data: [],
      editIndex: -1,
      loading: false
    };

    const el = {
      form: qs(formId),
      tbody: qs(tableBodyId),
      addBtn: qs(addBtnId),
      cancelBtn: qs(cancelBtnId),
      refreshBtn: qs(refreshBtnId),
      deleteAllBtn: qs(deleteAllBtnId)
    };

    // ---------- Utilities ----------
    function setLoading(b) {
      state.loading = !!b;
      if (el.addBtn) el.addBtn.disabled = b;
      if (el.refreshBtn) el.refreshBtn.disabled = b;
      if (el.deleteAllBtn) el.deleteAllBtn.disabled = b;
      if (el.cancelBtn) el.cancelBtn.disabled = b && state.editIndex >= 0;
    }

    function getFormValues() {
      const v = {};
      fields.forEach(f => {
        const node = qs(f.id);
        if (!node) return;
        let val = (node.value ?? "").toString().trim();
        if (f.requiredInvalidValue && val === f.requiredInvalidValue) val = "";
        v[f.key] = val;
      });
      return v;
    }

    function setFormValues(row) {
      fields.forEach(f => {
        const node = qs(f.id);
        if (!node) return;
        const val = row ? (row[f.key] ?? "") : "";
        node.value = val;
      });
    }

    function clearForm() { setFormValues(null); }

    function validate(values) {
      for (const f of fields) {
        const val = (values[f.key] ?? "").toString().trim();
        if (f.required && !val) {
          alert(`กรุณากรอก/เลือก ${f.label}`);
          qs(f.id)?.focus();
          return false;
        }
      }
      return true;
    }

    function setAddButtonMode() {
      if (!el.addBtn) return;
      const span = el.addBtn.querySelector("span");
      if (span) span.textContent = state.editIndex >= 0 ? "บันทึก" : "เพิ่มข้อมูล";
    }

    // ---------- Render ----------
    function renderEmptyRow() {
      const tr = document.createElement("tr");
      tr.className = "empty-row";
      const td = document.createElement("td");
      td.colSpan = Math.max(3, fields.length + 1);
      td.className = "text-center text-muted";
      td.textContent = "ไม่มีข้อมูล";
      tr.appendChild(td);
      return tr;
    }

    function renderRow(row, index) {
      const tr = document.createElement("tr");
      fields.forEach(f => {
        const td = document.createElement("td");
        if (f.key === "dept") {
          td.textContent = row.dept_name || row.dept || "";
        } else if (f.key === "slot") {
          td.textContent = row.slot_text || row.slot || "";
        } else {
          td.textContent = row[f.key] ?? "";
        }
        tr.appendChild(td);
      });

      // คอลัมน์จัดการ
      const act = document.createElement("td");
      act.className = "d-flex justify-content-center align-items-center gap-2";


      const btnEdit = document.createElement("button");
      btnEdit.type = "button";
      btnEdit.className = "btn-warning-gradient";
      btnEdit.textContent = "แก้ไข";
      btnEdit.addEventListener("click", () => {
        state.editIndex = index;
        setFormValues(row);
        if (el.cancelBtn) el.cancelBtn.classList.remove("d-none");
        setAddButtonMode();
      });

      const btnDel = document.createElement("button");
      btnDel.type = "button";
      btnDel.className = "btn-danger-gradient";
      btnDel.textContent = "ลบ";
      btnDel.addEventListener("click", async () => {
        if (!confirm("ต้องการลบรายการนี้หรือไม่?")) return;
        try {
          setLoading(true);
          await remote.remove(row.id);
          await reload();
        } catch (e) {
          console.error(e);
          alert(e.message || "ลบไม่สำเร็จ");
        } finally {
          setLoading(false);
        }
      });

      act.appendChild(btnEdit);
      act.appendChild(btnDel);
      tr.appendChild(act);

      return tr;
    }

    function renderTable() {
      if (!el.tbody) return;
      el.tbody.innerHTML = "";
      if (!state.data || state.data.length === 0) {
        el.tbody.appendChild(renderEmptyRow());
        return;
      }
      state.data.forEach((row, i) => el.tbody.appendChild(renderRow(row, i)));
    }

    // ---------- Actions ----------
    async function reload() {
      try {
        setLoading(true);
        const items = await remote.load();
        state.data = Array.isArray(items) ? items : (items?.items || []);
        state.editIndex = -1;
        if (el.cancelBtn) el.cancelBtn.classList.add("d-none");
        setAddButtonMode();
        renderTable();
      } catch (e) {
        console.error(e);
        alert(e.message || "โหลดข้อมูลไม่สำเร็จ");
      } finally {
        setLoading(false);
      }
    }

    async function submit() {
      const values = getFormValues();
      if (!validate(values)) return;

      try {
        setLoading(true);
        await remote.create(values);
        clearForm();
        state.editIndex = -1;
        if (el.cancelBtn) el.cancelBtn.classList.add("d-none");
        setAddButtonMode();
        await reload();
      } catch (e) {
        console.error(e);
        alert(e.message || "บันทึกไม่สำเร็จ");
      } finally {
        setLoading(false);
      }
    }

    function cancelEdit() {
      state.editIndex = -1;
      clearForm();
      if (el.cancelBtn) el.cancelBtn.classList.add("d-none");
      setAddButtonMode();
    }

    // ---------- Bind ----------
    if (el.addBtn) el.addBtn.addEventListener("click", submit);
    if (el.cancelBtn) el.cancelBtn.addEventListener("click", cancelEdit);
    if (el.refreshBtn) el.refreshBtn.addEventListener("click", reload);

    if (el.deleteAllBtn) el.deleteAllBtn.addEventListener("click", async () => {
      if (!remote.removeAll) {
        alert("ยังไม่ได้กำหนด remote.removeAll() ใน controller นี้");
        return;
      }
      if (!confirm("ต้องการลบทั้งหมดหรือไม่?")) return;
      try {
        setLoading(true);
        await remote.removeAll();
        await reload();
      } catch (e) {
        console.error(e);
        alert(e.message || "ลบทั้งหมดไม่สำเร็จ");
      } finally {
        setLoading(false);
      }
    });

    // เริ่มต้น
    setAddButtonMode();
    reload();

    return { state, reload, submit, cancelEdit };
  }

  global.makeController = makeController;

})(window);
