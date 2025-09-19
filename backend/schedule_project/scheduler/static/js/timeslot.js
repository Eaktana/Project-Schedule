// /static/js/timeslot.js
document.addEventListener('DOMContentLoaded', () => {
  // ---- CSRF + fetch helpers ----
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

  window.timeslotController = makeController({
    key:'timeslot',
    formId:'timeslotForm',
    fields:[
      {id:'ts_id',    key:'id',    label:'รหัสคาบ',   required:true},
      {id:'ts_day',   key:'day',   label:'วัน',       required:true, requiredInvalidValue:'เลือกวัน'},
      {id:'ts_start', key:'start', label:'เวลาเริ่ม', required:true},
      {id:'ts_end',   key:'end',   label:'เวลาสิ้นสุด', required:true},
    ],
    tableBodyId:'timeslotTableBody',
    addBtnId:'btnAddTimeSlot',
    cancelBtnId:'btnCancelTimeSlotEdit',
    refreshBtnId:'btnRefreshTimeSlot',

    remote: {
      async load(){
        const { items } = await apiGet('/api/timeslot/list/');
        return items; // [{id, day, start, end}, ...]
      },
      async create(values){
        const payload = {
          id:    Number(values.id),
          day:   String(values.day || '').trim(),   // ควรเป็น Mon/Tue/... หรือชื่อไทย
          start: String(values.start || '').trim(), // HH:MM
          end:   String(values.end || '').trim(),   // HH:MM
        };
        await apiPost('/api/timeslot/add/', payload); // upsert ตาม id
      },
      async remove(id){
        await apiDelete(`/api/timeslot/delete/${id}/`);
      }
    }
  });
});
