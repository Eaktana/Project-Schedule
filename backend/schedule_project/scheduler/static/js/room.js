// /static/js/room.js
document.addEventListener('DOMContentLoaded', () => {
  // ---- CSRF ----
  const csrftoken = (() => {
    const m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : '';
  })();

  // ---- Fetch Helpers ----
  async function apiGet(url) {
    const r = await fetch(url);
    const j = await r.json();
    if (!r.ok || j.status !== 'success') throw new Error(j.message || `HTTP ${r.status}`);
    return j;
  }
  async function apiPost(url, payload) {
    const r = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrftoken },
      body: JSON.stringify(payload),
    });
    const j = await r.json();
    if (!r.ok || j.status !== 'success') throw new Error(j.message || `HTTP ${r.status}`);
    return j;
  }
  async function apiDelete(url) {
    const r = await fetch(url, { method: 'DELETE', headers: { 'X-CSRFToken': csrftoken } });
    const j = await r.json();
    if (!r.ok || j.status !== 'success') throw new Error(j.message || `HTTP ${r.status}`);
    return j;
  }

  // ---- DOM ----
  const $id      = document.getElementById('room_id');
  const $name    = document.getElementById('room_name');
  const $type    = document.getElementById('room_type_select');
  const $add     = document.getElementById('btnAddRoom');
  const $cancel  = document.getElementById('btnCancelRoomEdit');
  const $tbody   = document.getElementById('roomTableBody');
  let   $refresh = document.getElementById('btnRefreshRoom'); // ใช้ปุ่มเดิม แต่จะเปลี่ยนหน้าที่เป็น "ลบทั้งหมด"

  // ---- State ----
  let editing = false;

  // ---- Load dropdown "ประเภทห้อง" จาก DB ----
  async function loadRoomTypes() {
    try {
      const { items } = await apiGet('/api/roomtype/list/');
      $type.innerHTML =
        '<option value="">-- เลือกประเภทห้อง --</option>' +
        items.map(x => `<option value="${x.id}">${x.name}</option>`).join('');
    } catch (e) {
      console.error(e);
      $type.innerHTML = '<option value="">(โหลดประเภทห้องไม่สำเร็จ)</option>';
    }
  }

  // ---- วาดตารางห้องจาก DB ----
  async function loadRooms() {
    try {
      const { items } = await apiGet('/api/room/list/');
      $tbody.innerHTML = '';
      if (!items.length) {
        $tbody.innerHTML =
          '<tr class="empty-row"><td colspan="4" class="text-center text-muted">ไม่มีข้อมูลห้องเรียน</td></tr>';
        return;
      }
      for (const r of items) {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${r.id}</td>
          <td>${r.name}</td>
          <td>${r.type_name || ''}</td>
          <td class="text-nowrap">
            <button class="btn btn-sm btn-outline-primary me-1" data-act="edit" data-id="${r.id}">แก้ไข</button>
            <button class="btn btn-sm btn-outline-danger" data-act="del" data-id="${r.id}">ลบ</button>
          </td>`;
        $tbody.appendChild(tr);
      }
    } catch (e) {
      console.error(e);
      $tbody.innerHTML =
        '<tr><td colspan="4" class="text-danger text-center">โหลดรายการห้องไม่สำเร็จ</td></tr>';
    }
  }

  // ---- เพิ่ม/บันทึก ----
  async function submitRoom() {
    const idVal   = String($id.value   || '').trim();
    const nameVal = String($name.value || '').trim();
    const typeVal = String($type.value || '').trim();

    if (!nameVal) { alert('กรอก "ชื่อห้องเรียน"'); return; }
    if (!typeVal) { alert('เลือก "ประเภทห้อง"'); return; }

    const payload = { name: nameVal, type: Number(typeVal) };
    if (idVal !== '') payload.id = Number(idVal); // upsert

    try {
      $add.disabled = true;
      $add.innerHTML = editing ? 'กำลังบันทึก...' : 'กำลังเพิ่ม...';
      await apiPost('/api/room/add/', payload);
      clearForm();
      await loadRooms();
    } catch (e) {
      alert(e.message || 'บันทึกไม่สำเร็จ');
      console.error(e);
    } finally {
      $add.disabled = false;
      $add.innerHTML = editing
        ? '<i class="bi bi-save me-2"></i>บันทึก'
        : '<i class="bi bi-plus-lg me-2"></i><span>เพิ่มข้อมูล</span>';
    }
  }

  // ---- ล้างฟอร์ม / ยกเลิกแก้ไข ----
  function clearForm() {
    $id.value = '';
    $name.value = '';
    $type.value = '';
    editing = false;
    $cancel.classList.add('d-none');
    $add.innerHTML = '<i class="bi bi-plus-lg me-2"></i><span>เพิ่มข้อมูล</span>';
  }

  // ---- ลบทั้งหมด (ใช้ helper + CSRF ที่เตรียมไว้) ----
  async function deleteAllRooms() {
    if (!confirm('ยืนยันลบห้องทั้งหมด?')) return;
    try {
      await apiDelete('/api/room/delete-all/');
      await loadRooms();
      alert('✅ ลบห้องทั้งหมดเรียบร้อยแล้ว');
    } catch (e) {
      alert(e.message || 'เกิดข้อผิดพลาดในการลบทั้งหมด');
      console.error(e);
    }
  }

  // ผูกปุ่มลบทั้งหมด (id ตรงกับใน room.html)
  const $delAll = document.getElementById('btnDeleteAllRoom');
  if ($delAll) {
    $delAll.addEventListener('click', deleteAllRooms);
  }

  // ผูกปุ่มเพิ่ม/ยกเลิก
  $cancel.addEventListener('click', clearForm);
  $add.addEventListener('click', submitRoom);

  // ---- init: ดึงข้อมูลจาก DB ตอนเปิดหน้า ----
  (async () => {
    await loadRoomTypes();  // GET /api/roomtype/list/
    await loadRooms();      // GET /api/room/list/
  })();
});
