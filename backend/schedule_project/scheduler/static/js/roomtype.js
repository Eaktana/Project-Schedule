// /static/js/roomtype.js
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

  window.roomTypeController = makeController({
    key:'roomtype',
    formId:'roomTypeForm',
    fields:[
      {id:'roomtype_id',   key:'id',   label:'รหัสประเภทห้อง', required:false},
      {id:'roomtype_name', key:'name', label:'ชื่อประเภทห้อง', required:true},
    ],
    tableBodyId:'roomTypeTableBody',
    addBtnId:'btnAddRoomType',
    cancelBtnId:'btnCancelRoomTypeEdit',
    deleteAllBtnId:'btnDeleteAllRoomType',

    remote: {
      async load(){
        const { items } = await apiGet('/api/roomtype/list/');
        return items; // [{id, name}, ...]
      },
      async create(values){
        const payload = { name: String(values.name || '').trim() };
        if (String(values.id || '').trim() !== '') payload.id = Number(values.id);
        await apiPost('/api/roomtype/add/', payload);
      },
      async remove(id){
        await apiDelete(`/api/roomtype/delete/${id}/`);
      },
      async removeAll(){                      
      await apiDelete('/api/roomtype/delete-all/');
      }
    }
  });
});
