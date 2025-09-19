// /static/js/grouptype.js
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

  // ---- hook เข้า controller ----
  window.groupTypeController = makeController({
    key:'grouptype',
    formId:'groupTypeForm',
    fields:[
      {id:'dept_id',      key:'id',   label:'รหัสภาค',        required:true},
      {id:'student_type', key:'type', label:'ประเภทนักศึกษา', required:true, requiredInvalidValue:'เลือกประเภท'},
    ],
    tableBodyId:'groupTypeTableBody',
    addBtnId:'btnAddGroupType',
    cancelBtnId:'btnCancelGroupTypeEdit',
    deleteAllBtnId:'btnDeleteAllGroupType',   // ✅ ใช้ปุ่มลบทั้งหมดแทน refresh

    remote: {
      async load(){
        const { items } = await apiGet('/api/grouptype/list/');
        // items: [{id, type}, ...]
        return items;
      },
      async create(values){
        const payload = { id: Number(values.id), type: String(values.type || '').trim() };
        await apiPost('/api/grouptype/add/', payload);
      },
      async remove(id){
        await apiDelete(`/api/grouptype/delete/${id}/`);
      },
      async removeAll(){
        await apiDelete('/api/grouptype/delete-all/');   // ✅ backend รองรับแล้ว
      }
    }
  });
});
