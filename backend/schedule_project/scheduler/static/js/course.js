// ===== helper: set selected value on <select> =====
function setSelectValue(sel, val) {
  if (!sel) return;
  const hit = [...sel.options].find(o => o.value === val || o.text === val);
  if (hit) sel.value = hit.value;
  else if (val !== undefined && val !== null && String(val).trim() !== '') {
    const opt = document.createElement('option');
    opt.value = val;
    opt.text = val;
    sel.appendChild(opt);
    sel.value = val;
  }
}

// ===== notification system (เหมือน pre.js สไตล์) =====
function showNotification(message, type='info', duration=5000){
  const container = document.getElementById('notificationContainer');
  const notification = document.createElement('div');
  const typeMap = {success:'success', error:'error', warning:'warning', info:'info', debug:'info'};
  const notificationType = typeMap[type] || 'info';

  notification.className = `notification ${notificationType}`;
  notification.innerHTML = `
    <button class="notification-close" onclick="closeNotification(this)">&times;</button>
    <div>${message}</div>
    <div class="notification-progress"></div>
  `;
  container.appendChild(notification);

  setTimeout(()=>notification.classList.add('show'),100);

  const progressBar = notification.querySelector('.notification-progress');
  progressBar.style.width = '100%';
  setTimeout(()=>{ progressBar.style.width='0%'; progressBar.style.transitionDuration = duration+'ms'; }, 100);

  setTimeout(()=> closeNotification(notification.querySelector('.notification-close')), duration);
}
function closeNotification(button){
  const notification = button.parentElement;
  notification.style.opacity='0';
  notification.style.transform='translateX(100%)';
  setTimeout(()=>{ if(notification.parentElement){ notification.parentElement.removeChild(notification); } }, 300);
}

// ===== csrf helper =====
function getCookie(name){
  let cookieValue=null;
  if(document.cookie && document.cookie!==''){
    const cookies=document.cookie.split(';');
    for(let i=0;i<cookies.length;i++){
      const cookie=cookies[i].trim();
      if(cookie.substring(0, name.length+1)===(name+'=')){
        cookieValue=decodeURIComponent(cookie.substring(name.length+1));
        break;
      }
    }
  }
  return cookieValue;
}

// ===== AJAX helper to populate selects (รับรูปแบบ {results: [...]}) =====
async function populateSelect(url, selectId, mapItem) {
  const sel = document.getElementById(selectId);
  if (!sel) return;
  const prev = sel.value;
  sel.innerHTML = '<option value="">กำลังโหลด...</option>';
  try {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const payload = await r.json();
    const results = Array.isArray(payload) ? payload : (payload.results || payload.items);
    sel.innerHTML = '<option value="">เลือก</option>';
    (results || []).forEach(item => {
      const opt = document.createElement('option');
      const { value, label, dataset } = mapItem(item);
      opt.value = value; opt.textContent = label;
      if (dataset) Object.entries(dataset).forEach(([k, v]) => opt.dataset[k] = v);
      sel.appendChild(opt);
    });
    // keep previous value if exists
    if (prev) setSelectValue(sel, prev);
  } catch (e) {
    console.error(`Populate ${selectId} fail:`, e);
    sel.innerHTML = '<option value="">โหลดไม่สำเร็จ</option>';
  }
}

// ===== sync subject code/name แบบใช้ dataset.sid (เหมือน pre.js) =====
function wireSubjectCodeNameSync(codeSelId, nameSelId) {
  const codeSel = document.getElementById(codeSelId);
  const nameSel = document.getElementById(nameSelId);
  if (!codeSel || !nameSel) return;

  codeSel.addEventListener('change', () => {
    const codeOpt = codeSel.selectedOptions[0];
    if (!codeOpt) return;
    const sid = codeOpt.dataset.sid;
    if (!sid) return;
    const match = [...nameSel.options].find(o => o.dataset.sid === sid);
    if (match) nameSel.value = match.value;
  });

  nameSel.addEventListener('change', () => {
    const nameOpt = nameSel.selectedOptions[0];
    if (!nameOpt) return;
    const sid = nameOpt.dataset.sid;
    if (!sid) return;
    const match = [...codeSel.options].find(o => o.dataset.sid === sid);
    if (match) codeSel.value = match.value;
  });
}

// ===== CRUD: เพิ่มข้อมูลรายวิชา =====
function addCourse(){
  const payload = {
    teacher_id                 : document.getElementById("teacher_select").value,
    subject_code_course        : document.getElementById("subject_code_select").value,
    subject_name_course        : document.getElementById("subject_name_select").value,
    room_type_course           : document.getElementById("room_type_select").value,
    section_course             : document.getElementById("section").value,
    student_group_id           : document.getElementById("student_group_select").value,
    theory_slot_amount_course  : Number(document.getElementById("theory_hours").value || 0),
    lab_slot_amount_course     : Number(document.getElementById("lab_hours").value || 0)
  };

  if(!payload.teacher_id || !payload.subject_code_course || !payload.subject_name_course){
    showNotification('กรุณาเลือก: อาจารย์ และ รหัสวิชา/ชื่อวิชา','warning'); 
    return;
  }

  fetch('/api/course/add/', {
    method:'POST',
    headers:{'Content-Type':'application/json','X-CSRFToken': getCookie('csrftoken')},
    body: JSON.stringify(payload)
  })
  .then(r=>r.json())
  .then(d=>{
    if(d.status==='success'){ showNotification('✅ เพิ่มข้อมูลรายวิชาสำเร็จ','success'); location.reload(); }
    else{ showNotification('เกิดข้อผิดพลาด: '+(d.message||'ไม่สามารถเพิ่มข้อมูลได้'),'error'); }
  })
  .catch(()=> showNotification('เกิดข้อผิดพลาดในการเพิ่มข้อมูล','error'));
}

// ===== ลบ =====
function confirmDelete(button){
  if(confirm("คุณแน่ใจหรือไม่ว่าต้องการลบรายการนี้?")){
    const row = button.closest("tr");
    const id  = row.getAttribute("data-id");

    fetch(`/api/course/delete/${id}/`, {
      method:'DELETE',
      headers:{ 'X-CSRFToken': getCookie('csrftoken') }
    })
    .then(r=>r.json())
    .then(d=>{
      if(d.status==='success'){ row.remove(); showNotification("✅ ลบข้อมูลเรียบร้อยแล้ว",'success'); }
      else{ showNotification('เกิดข้อผิดพลาดในการลบข้อมูล','error'); }
    })
    .catch(()=> showNotification('เกิดข้อผิดพลาดในการลบข้อมูล','error'));
  }
}

// ===== แก้ไข =====
let editRow = null;
let editId  = null;
function openEditModal(button){
  editRow = button.closest("tr");
  editId  = editRow.getAttribute("data-id");
  const cells = editRow.getElementsByTagName("td");

  // ตั้งค่า dropdown/inputs จากค่าที่แสดงในตาราง (ใช้ setSelectValue สำหรับฟิลด์ที่โหลด async)
  setSelectValue(document.getElementById("editTeacherSelect"), cells[0].innerText.trim());
  setSelectValue(document.getElementById("editSubjectCodeSelect"), cells[1].querySelector('.badge').innerText.trim());
  setSelectValue(document.getElementById("editSubjectNameSelect"), cells[2].innerText.trim());
  setSelectValue(document.getElementById("editRoomTypeSelect"), cells[3].innerText.trim());
  document.getElementById("editSection").value = cells[4].innerText.trim();
  setSelectValue(document.getElementById("editStudentGroupSelect"), cells[5].innerText.trim());
  document.getElementById("editTheoryHours").value = Number(cells[6].innerText.trim()) || 0;
  document.getElementById("editLabHours").value = Number(cells[7].innerText.trim()) || 0;

  new bootstrap.Modal(document.getElementById("editModal")).show();
}

function saveEdit(){
  const payload = {
    teacher_id                 : document.getElementById("editTeacherSelect").value,
    subject_code_course        : document.getElementById("editSubjectCodeSelect").value,
    subject_name_course        : document.getElementById("editSubjectNameSelect").value,
    room_type_course           : document.getElementById("editRoomTypeSelect").value,
    section_course             : document.getElementById("editSection").value,
    student_group_id           : document.getElementById("editStudentGroupSelect").value,
    theory_slot_amount_course  : Number(document.getElementById("editTheoryHours").value || 0),
    lab_slot_amount_course     : Number(document.getElementById("editLabHours").value || 0)
  };

  fetch(`/api/course/update/${editId}/`, {
    method:'PUT',
    headers:{'Content-Type':'application/json','X-CSRFToken': getCookie('csrftoken')},
    body: JSON.stringify(payload)
  })
  .then(r=>r.json())
  .then(d=>{
    if(d.status==='success'){
      showNotification("✅ แก้ไขข้อมูลเรียบร้อยแล้ว",'success');
      bootstrap.Modal.getInstance(document.getElementById("editModal")).hide();
      location.reload();
    }else{
      showNotification('เกิดข้อผิดพลาดในการแก้ไขข้อมูล','error');
    }
  })
  .catch(()=> showNotification('เกิดข้อผิดพลาดในการแก้ไขข้อมูล','error'));
}

function refreshData(){ location.reload(); }

// ===== init wiring (pattern เดียวกับ pre.js) =====
document.addEventListener('DOMContentLoaded', async () => {
  // --- Add Form dropdowns ---
  await populateSelect('/api/teachers/', 'teacher_select', t => ({ value: t.value ?? t.id, label: t.label ?? t.name }));
  await populateSelect('/api/subjects/', 'subject_code_select', s => ({ value: s.code, label: s.code, dataset:{ sid:String(s.id ?? s.sid ?? s.code) } }));
  await populateSelect('/api/subjects/', 'subject_name_select', s => ({ value: s.name, label: s.name, dataset:{ sid:String(s.id ?? s.sid ?? s.code) } }));
  wireSubjectCodeNameSync('subject_code_select','subject_name_select');
  await populateSelect('/api/lookups/room-types/','room_type_select', i => ({ value: i.name, label: i.name }));
  await populateSelect('/api/lookups/student-groups/', 'student_group_select', i => ({ value: i.name, label: i.name }));

  // --- Edit Modal dropdowns ---
  await populateSelect('/api/teachers/', 'editTeacherSelect', t => ({ value: t.value ?? t.id, label: t.label ?? t.name }));
  await populateSelect('/api/subjects/', 'editSubjectCodeSelect', s => ({ value: s.code, label: s.code, dataset:{ sid:String(s.id ?? s.sid ?? s.code) } }));
  await populateSelect('/api/subjects/', 'editSubjectNameSelect', s => ({ value: s.name, label: s.name, dataset:{ sid:String(s.id ?? s.sid ?? s.code) } }));
  wireSubjectCodeNameSync('editSubjectCodeSelect','editSubjectNameSelect');
  await populateSelect('/api/lookups/room-types/','editRoomTypeSelect', i => ({ value: i.name, label: i.name }));
  await populateSelect('/api/lookups/student-groups/','editStudentGroupSelect', i => ({ value: i.name, label: i.name }));

  showNotification("ยินดีต้อนรับสู่หน้าจัดการข้อมูลรายวิชา", 'info');
});
