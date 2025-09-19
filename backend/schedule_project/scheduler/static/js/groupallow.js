// static/js/groupallow.js
document.addEventListener('DOMContentLoaded', () => {
  // ---- helpers fetch + CSRF ----
  const csrftoken = (() => {
    const m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : '';
  })();

  async function apiGet(url){
    const r = await fetch(url);
    const j = await r.json();
    if (!r.ok || j.status !== 'success') throw new Error(j.message || `HTTP ${r.status}`);
    return j;
  }
  async function apiPost(url, payload){
    const r = await fetch(url, {
      method: 'POST',
      headers: {'Content-Type':'application/json','X-CSRFToken': csrftoken},
      body: JSON.stringify(payload)
    });
    const j = await r.json();
    if (!r.ok || j.status !== 'success') throw new Error(j.message || `HTTP ${r.status}`);
    return j;
  }
  async function apiDelete(url){
    const r = await fetch(url, { method: 'DELETE', headers: {'X-CSRFToken': csrftoken} });
    const j = await r.json();
    if (!r.ok || j.status !== 'success') throw new Error(j.message || `HTTP ${r.status}`);
    return j;
  }

  // ---- เติม dropdown <select> ----
  async function loadDepartments(){
    try{
      const { items } = await apiGet('/api/grouptype/list/');
      const sel = document.getElementById('ga_dept_id');
      sel.innerHTML = '<option value="">-- เลือกภาค --</option>' +
        items.map(x => `<option value="${x.id}">${x.id} — ${x.type}</option>`).join('');
    }catch(err){
      console.error(err);
      const sel = document.getElementById('ga_dept_id');
      if (sel) sel.innerHTML = '<option value="">(โหลดภาคไม่สำเร็จ)</option>';
    }
  }

  async function loadTimeSlots(){
    try{
      const { items } = await apiGet('/api/timeslot/list/');
      const sel = document.getElementById('ga_slot_id');
      sel.innerHTML = '<option value="">-- เลือกคาบ --</option>' +
        items.map(x => `<option value="${x.id}">${x.day} ${x.start}-${x.end}</option>`).join('');
    }catch(err){
      console.error(err);
      const sel = document.getElementById('ga_slot_id');
      if (sel) sel.innerHTML = '<option value="">(โหลดคาบไม่สำเร็จ)</option>';
    }
  }

  // โหลด dropdown ทั้งคู่
  loadDepartments();
  loadTimeSlots();

  // ---- hook เข้า controller ----
  window.groupAllowController = makeController({
    key:'groupallow',
    formId:'groupAllowForm',
    fields:[
      {id:'ga_dept_id', key:'dept', label:'รหัสภาค', required:true},
      {id:'ga_slot_id', key:'slot', label:'รหัสคาบ', required:true},
    ],
    tableBodyId:'groupAllowTableBody',
    addBtnId:'btnAddGroupAllow',
    cancelBtnId:'btnCancelGroupAllowEdit',
    deleteAllBtnId:'btnDeleteAllGroupAllow',   // ✅ ใช้ปุ่มลบทั้งหมด

    remote: {
      async load(){
        const { items } = await apiGet('/api/groupallow/list/');
        return items; // [{id, dept, slot, dept_name?, slot_text?}, ...]
      },
      async create(values){
        const payload = { dept: Number(values.dept), slot: Number(values.slot) };

        // ถ้าอยู่โหมดแก้ไข: ลบของเดิมก่อน (unique_together)
        const idx = groupAllowController.state.editIndex;
        if (idx >= 0){
          const row = groupAllowController.state.data[idx];
          if (row && row.id != null){
            await apiDelete(`/api/groupallow/delete/${row.id}/`);
          }
        }
        await apiPost('/api/groupallow/add/', payload);
      },
      async remove(id){
        await apiDelete(`/api/groupallow/delete/${id}/`);
      },
      async removeAll(){
        // ✅ ต้องมี endpoint ฝั่ง backend รองรับ
        await apiDelete('/api/groupallow/delete-all/');
      }
    }
  });
});
