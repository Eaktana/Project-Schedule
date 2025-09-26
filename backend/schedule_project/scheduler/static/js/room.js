// /static/js/room.js
document.addEventListener('DOMContentLoaded', () => {
  /* ===================== CSRF ===================== */
  const csrftoken = (() => {
    const m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : '';
  })();

  /* ===================== Fetch Helpers ===================== */
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
      body: JSON.stringify(payload ?? {}),
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

  /* ===================== DOM refs ===================== */
  const $name    = document.getElementById('room_name');
  const $type    = document.getElementById('room_type_select');
  const $add     = document.getElementById('btnAddRoom');
  const $cancel  = document.getElementById('btnCancelRoomEdit');
  const $tbody   = document.getElementById('roomTableBody');
  const $delAll  = document.getElementById('btnDeleteAllRoom');

  /* ===================== State ===================== */
  let editing = false;
  let editingId = null;         // เก็บ id เฉพาะตอน "แก้ไข"
  let roomsCache = [];          // เก็บรายการล่าสุดจาก /api/room/list/ เพื่อใช้ตอนกดแก้ไข

  /* ===================== Load dropdown ประเภทห้อง ===================== */
  async function loadRoomTypes() {
    try {
      // GET /api/roomtype/list/
      const { items } = await apiGet('/api/roomtype/list/'); /* endpoints ตาม urls.py */ /*:contentReference[oaicite:2]{index=2}*/
      $type.innerHTML =
        '<option value="">-- เลือกประเภทห้อง --</option>' +
        items.map(x => `<option value="${x.id}">${x.name}</option>`).join('');
    } catch (e) {
      console.error(e);
      $type.innerHTML = '<option value="">(โหลดประเภทห้องไม่สำเร็จ)</option>';
    }
  }

  /* ===================== วาดตารางห้อง ===================== */
  async function loadRooms() {
    try {
      // GET /api/room/list/
      const { items } = await apiGet('/api/room/list/');     /* endpoints ตาม urls.py */ /*:contentReference[oaicite:3]{index=3}*/
      roomsCache = items || [];
      $tbody.innerHTML = '';
      if (!roomsCache.length) {
        $tbody.innerHTML =
          '<tr class="empty-row"><td colspan="3" class="text-center text-muted">ไม่มีข้อมูลห้องเรียน</td></tr>';
        return;
      }
      for (const r of roomsCache) {
        // คอลัมน์แรกเป็น "ชื่อห้องเรียน" ไม่ใช่ id
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${escapeHtml(r.name ?? '')}</td>
          <td>${escapeHtml(r.type_name ?? '')}</td>
          <td class="d-flex justify-content-center gap-2">
            <button class="btn-warning-gradient" data-act="edit" data-id="${r.id}">แก้ไข</button>
            <button class="btn-danger-gradient" data-act="del"  data-id="${r.id}">ลบ</button>
          </td>`;
        $tbody.appendChild(tr);
      }
    } catch (e) {
      console.error(e);
      $tbody.innerHTML =
        '<tr><td colspan="3" class="text-danger text-center">โหลดรายการห้องไม่สำเร็จ</td></tr>';
    }
  }

  /* ===================== เพิ่ม/บันทึก ===================== */
  async function submitRoom() {
    const nameVal = String($name.value || '').trim();
    const typeVal = String($type.value || '').trim();

    if (!nameVal) { alert('กรอก "ชื่อห้องเรียน"'); return; }
    if (!typeVal) { alert('เลือก "ประเภทห้อง"'); return; }

    // ============ เพิ่มใหม่ ============
    // ไม่ส่ง id ให้ DB: ให้ DB/ORM สร้างอัตโนมัติ
    const payload = { name: nameVal, type: Number(typeVal) };

    // ============ แก้ไข ============
    // ใช้ upsert เดิมของ backend: ส่ง id เฉพาะตอนแก้ไข (front-end ไม่แสดง id)
    if (editing && editingId != null) {
      payload.id = Number(editingId);
    }

    try {
      $add.disabled = true;
      $add.innerHTML = editing ? 'กำลังบันทึก...' : 'กำลังเพิ่ม...';

      // POST /api/room/add/ (รองรับเพิ่ม + upsert ฝั่ง server)
      await apiPost('/api/room/add/', payload);           /* ตามรูปแบบ room.js เดิม */ /*:contentReference[oaicite:4]{index=4}*/

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

  /* ===================== ล้างฟอร์ม/ออกจากโหมดแก้ไข ===================== */
  function clearForm() {
    $name.value = '';
    $type.value = '';
    editing = false;
    editingId = null;
    $cancel.classList.add('d-none');
    $add.innerHTML = '<i class="bi bi-plus-lg me-2"></i><span>เพิ่มข้อมูล</span>';
  }

  /* ===================== ลบทั้งหมด ===================== */
  async function deleteAllRooms() {
    if (!confirm('ยืนยันลบห้องทั้งหมด?')) return;
    try {
      // DELETE /api/room/delete-all/
      await apiDelete('/api/room/delete-all/');           /* endpoints ตาม urls.py */ /*:contentReference[oaicite:5]{index=5}*/
      await loadRooms();
      alert('✅ ลบห้องทั้งหมดเรียบร้อยแล้ว');
    } catch (e) {
      alert(e.message || 'เกิดข้อผิดพลาดในการลบทั้งหมด');
      console.error(e);
    }
  }

  /* ===================== Event Delegation: edit / delete ===================== */
  $tbody.addEventListener('click', async (ev) => {
    const btn = ev.target.closest('button[data-act]');
    if (!btn) return;
    const act = btn.getAttribute('data-act');
    const id  = btn.getAttribute('data-id');

    if (act === 'edit') {
      const row = roomsCache.find(x => String(x.id) === String(id));
      if (!row) return;

      // ใส่ค่าในฟอร์ม
      $name.value = row.name ?? '';

      // พยายามเลือก option ตาม "type id" ก่อน ถ้าไม่มีให้แมตช์ด้วยชื่อ
      const typeId = row.type_id ?? row.room_type_id ?? row.type ?? null;
      if (typeId != null && $type.querySelector(`option[value="${typeId}"]`)) {
        $type.value = String(typeId);
      } else {
        // fallback: เทียบชื่อ
        const wanted = (row.type_name ?? '').trim();
        let matched = false;
        for (const opt of $type.options) {
          if (opt.text.trim() === wanted && opt.value) {
            $type.value = opt.value;
            matched = true;
            break;
          }
        }
        if (!matched) $type.value = '';
      }

      // เข้าโหมดแก้ไข
      editing = true;
      editingId = Number(id);
      $cancel.classList.remove('d-none');
      $add.innerHTML = '<i class="bi bi-save me-2"></i>บันทึก';
      $name.focus();
    }

    if (act === 'del') {
      if (!confirm('ลบรายการนี้หรือไม่?')) return;
      try {
        // DELETE /api/room/delete/<id>/
        await apiDelete(`/api/room/delete/${id}/`);       /* endpoints ตาม urls.py */ /*:contentReference[oaicite:6]{index=6}*/
        await loadRooms();
      } catch (e) {
        alert(e.message || 'ลบไม่สำเร็จ');
        console.error(e);
      }
    }
  });

  /* ===================== Misc helpers ===================== */
  function escapeHtml(s) {
    return String(s ?? '')
      .replace(/&/g,'&amp;')
      .replace(/</g,'&lt;')
      .replace(/>/g,'&gt;')
      .replace(/"/g,'&quot;')
      .replace(/'/g,'&#39;');
  }

  /* ===================== Bindings ===================== */
  $add.addEventListener('click', submitRoom);
  $cancel.addEventListener('click', clearForm);
  if ($delAll) $delAll.addEventListener('click', deleteAllRooms);

  /* ===================== Init ===================== */
  (async () => {
    await loadRoomTypes();   // /api/roomtype/list/
    await loadRooms();       // /api/room/list/
  })();
});
