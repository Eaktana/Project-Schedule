// /static/js/studentgroup.js
document.addEventListener('DOMContentLoaded', () => {
  // --- CSRF ---
  const csrftoken = (() => {
    const m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : '';
  })();

  // --- Helpers ---
  async function apiGet(url) {
    const r = await fetch(url);
    const j = await r.json();
    if (!r.ok || j.status && j.status !== 'success') {
      throw new Error(j.message || `HTTP ${r.status}`);
    }
    return j;
  }
  async function apiPost(url, payload) {
    const r = await fetch(url, {
      method: 'POST',
      headers: {'Content-Type':'application/json','X-CSRFToken': csrftoken},
      body: JSON.stringify(payload)
    });
    const j = await r.json();
    if (!r.ok || j.status !== 'success') throw new Error(j.message || `HTTP ${r.status}`);
    return j;
  }
  async function apiDelete(url) {
    const r = await fetch(url, { method: 'DELETE', headers: { 'X-CSRFToken': csrftoken }});
    const j = await r.json();
    if (!r.ok || j.status !== 'success') throw new Error(j.message || `HTTP ${r.status}`);
    return j;
  }

  // --- DOM refs ---
  const $id = document.getElementById('group_id');
  const $name = document.getElementById('group_name');
  const $type = document.getElementById('group_type');
  const $add = document.getElementById('btnAddStudentGroup');
  const $cancel = document.getElementById('btnCancelStudentGroupEdit');
  const $refresh = document.getElementById('btnRefreshStudentGroup');
  const $tbody = document.getElementById('studentGroupTableBody');

  let editing = false;

  // --- Load GroupType -> dropdown ---
  async function loadGroupTypes() {
    try {
      // /api/grouptype/list/ -> {"status":"success","items":[{"id", "type"}, ...]}
      const { items } = await apiGet('/api/grouptype/list/');
      $type.innerHTML = `<option value="">เลือกประเภท</option>` +
        items.map(x => `<option value="${x.id}">${x.type}</option>`).join('');
    } catch (e) {
      console.error(e);
      $type.innerHTML = `<option value="">(โหลดประเภทนักศึกษาไม่สำเร็จ)</option>`;
    }
  }

  // --- Load StudentGroup -> table ---
  async function loadStudentGroups() {
    try {
      // /api/studentgroup/list/ -> {"status":"success","items":[{id,name,type,type_name},...]}
      const { items } = await apiGet('/api/studentgroup/list/');
      $tbody.innerHTML = '';
      if (!items.length) {
        $tbody.innerHTML = `<tr class="empty-row"><td colspan="4" class="text-center text-muted">ไม่มีข้อมูลกลุ่มนักศึกษา</td></tr>`;
        return;
      }
      for (const row of items) {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${row.id}</td>
          <td>${row.name}</td>
          <td>${row.type_name || ''}</td>
          <td class="text-nowrap">
            <button class="btn btn-sm btn-outline-primary me-1" data-act="edit" data-id="${row.id}">แก้ไข</button>
            <button class="btn btn-sm btn-outline-danger" data-act="del" data-id="${row.id}">ลบ</button>
          </td>
        `;
        $tbody.appendChild(tr);
      }
    } catch (e) {
      console.error(e);
      $tbody.innerHTML = `<tr><td colspan="4" class="text-danger text-center">โหลดรายการไม่สำเร็จ</td></tr>`;
    }
  }

  // --- Submit (Add/Save) ---
  async function submitStudentGroup() {
    const idVal = String($id.value || '').trim();
    const nameVal = String($name.value || '').trim();
    const typeVal = String($type.value || '').trim();

    if (!idVal)   { alert('กรอกรหัสกลุ่มนักศึกษา'); return; }
    if (!nameVal) { alert('กรอกชื่อกลุ่มนักศึกษา'); return; }
    if (!typeVal) { alert('เลือกประเภทนักศึกษา');  return; }

    const payload = {
      id: Number(idVal),      // views ฝั่ง backend “บังคับให้ส่ง id” เพื่อ upsert ตาม pk
      name: nameVal,
      type: Number(typeVal),  // ต้องเป็น id ของ GroupType
    };
    try {
      $add.disabled = true;
      $add.innerHTML = editing ? 'กำลังบันทึก...' : 'กำลังเพิ่ม...';
      await apiPost('/api/studentgroup/add/', payload);
      clearForm();
      await loadStudentGroups();
    } catch (e) {
      alert(e.message || 'บันทึกไม่สำเร็จ');
      console.error(e);
    } finally {
      $add.disabled = false;
      $add.innerHTML = editing ? '<i class="bi bi-save me-2"></i>บันทึก' : '<i class="bi bi-plus-lg me-2"></i><span>เพิ่มข้อมูล</span>';
    }
  }

  function clearForm() {
    $id.value = '';
    $name.value = '';
    $type.value = '';
    editing = false;
    $cancel.classList.add('d-none');
    $add.innerHTML = '<i class="bi bi-plus-lg me-2"></i><span>เพิ่มข้อมูล</span>';
  }

  // --- Table actions: edit / delete ---
  $tbody.addEventListener('click', async (ev) => {
    const btn = ev.target.closest('[data-act]');
    if (!btn) return;
    const act = btn.getAttribute('data-act');
    const gid = btn.getAttribute('data-id');

    if (act === 'del') {
      if (!confirm('ยืนยันการลบกลุ่มนักศึกษานี้?')) return;
      try {
        await apiDelete(`/api/studentgroup/delete/${gid}/`);
        await loadStudentGroups();
      } catch (e) {
        alert(e.message || 'ลบไม่สำเร็จ');
      }
      return;
    }

    if (act === 'edit') {
      try {
        const { items } = await apiGet('/api/studentgroup/list/');
        const found = items.find(x => String(x.id) === String(gid));
        if (found) {
          $id.value = found.id;
          $name.value = found.name;
          $type.value = String(found.type || '');
          editing = true;
          $cancel.classList.remove('d-none');
          $add.innerHTML = '<i class="bi bi-save me-2"></i>บันทึก';
        }
      } catch (e) {
        console.error(e);
      }
    }
  });

    // --- Delete All ---
  async function deleteAllStudentGroups() {
    if (!confirm('คุณแน่ใจหรือไม่ว่าต้องการลบกลุ่มนักศึกษาทั้งหมด?')) return;
    try {
      await apiDelete('/api/studentgroup/delete-all/');  // ⚠️ ต้องมี endpoint ฝั่ง backend
      await loadStudentGroups();
      alert('✅ ลบกลุ่มนักศึกษาทั้งหมดเรียบร้อยแล้ว');
    } catch (e) {
      alert(e.message || 'เกิดข้อผิดพลาดในการลบทั้งหมด');
      console.error(e);
    }
  }

  // --- wire events ---
  $add.addEventListener('click', submitStudentGroup);
  $cancel.addEventListener('click', clearForm);

  const $deleteAll = document.getElementById('btnDeleteAllStudentGroup');
  if ($deleteAll) {
    $deleteAll.addEventListener('click', deleteAllStudentGroups);
  }

  // --- init ---
  (async () => {
    await loadGroupTypes();
    await loadStudentGroups();
  })();



  // --- wire events ---
  $add.addEventListener('click', submitStudentGroup);
  $cancel.addEventListener('click', clearForm);
  $deleteAll.addEventListener('click', loadStudentGroups);

  // --- init ---
  (async () => {
    await loadGroupTypes();
    await loadStudentGroups();
  })();
});
