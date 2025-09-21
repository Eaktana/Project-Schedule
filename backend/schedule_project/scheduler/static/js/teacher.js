// /static/js/teacher.js
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

  window.teacherController = makeController({
    key:'teacher',
    formId:'teacherForm',
    fields:[
      {id:'teacher_id',   key:'id',   label:'รหัสอาจารย์', required:true},
      {id:'teacher_name', key:'name', label:'ชื่ออาจารย์', required:true},
    ],
    tableBodyId:'teacherTableBody',
    addBtnId:'btnAddTeacher',
    cancelBtnId:'btnCancelTeacherEdit',
    deleteAllBtnId:'btnDeleteAllTeacher',   // ✅ ใช้ปุ่มลบทั้งหมดแทน refresh

    remote: {
      async load(){
        const { items } = await apiGet('/api/teacher/list/');
        return items;
      },
      async create(values){
        const payload = {
          id:   Number(values.id),
          name: String(values.name || '').trim(),
        };
        await apiPost('/api/teacher/add/', payload);
      },
      async remove(id){
        await apiDelete(`/api/teacher/delete/${id}/`);
      },
      async removeAll(){                         // ✅ เพิ่ม removeAll
        await apiDelete('/api/teacher/delete-all/');
      }
    }
  });
});
