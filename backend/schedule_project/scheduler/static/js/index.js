"use strict";

/* ===== Utilities ===== */
function getCookie(name){
  let cookieValue=null;
  if(document.cookie && document.cookie!==""){
    const cookies=document.cookie.split(";");
    for(let i=0;i<cookies.length;i++){
      const cookie=cookies[i].trim();
      if(cookie.substring(0,name.length+1)===name+"="){
        cookieValue=decodeURIComponent(cookie.substring(name.length+1)); break;
      }
    }
  }
  return cookieValue;
}

/* ===== Generate schedule ===== */
function generateSchedule(){
  if(!confirm("คุณต้องการสร้างตารางสอนใหม่หรือไม่?")) return;
  fetch("/api/schedule/generate/",{
    method:"POST",
    headers:{ "Content-Type":"application/json", "X-CSRFToken": getCookie("csrftoken") }
  })
  .then(r=>r.json())
  .then(d=>{
    if(d.status==="success"){ alert("สร้างตารางสอนสำเร็จแล้ว!"); location.reload(); }
    else{ alert("เกิดข้อผิดพลาด: "+d.message); }
  })
  .catch(e=>{ console.error(e); alert("เกิดข้อผิดพลาดในการสร้างตารางสอน"); });
}

/* ===== Schedule Modal (grid/list) ===== */
(function(){
  const DAY_ORDER=["จันทร์","อังคาร","พุธ","พฤหัสบดี","ศุกร์","เสาร์","อาทิตย์"];
  const START_HOUR=8, END_HOUR=21;

  let SCHEDULES=null, selectedCategory="Teacher", selectedItem="", searchTerm="", viewMode="grid", filtered=[];

  const DAY_MAP={
    'จันทร์':'จันทร์','จ.':'จันทร์','mon':'จันทร์','monday':'จันทร์','1':'จันทร์',
    'อังคาร':'อังคาร','อ.':'อังคาร','tue':'อังคาร','tuesday':'อังคาร','2':'อังคาร',
    'พุธ':'พุธ','พ.':'พุธ','wed':'พุธ','wednesday':'พุธ','3':'พุธ',
    'พฤหัสบดี':'พฤหัสบดี','พฤ.':'พฤหัสบดี','thu':'พฤหัสบดี','thursday':'พฤหัสบดี','4':'พฤหัสบดี',
    'ศุกร์':'ศุกร์','ศ.':'ศุกร์','fri':'ศุกร์','friday':'ศุกร์','5':'ศุกร์',
    'เสาร์':'เสาร์','ส.':'เสาร์','sat':'เสาร์','saturday':'เสาร์','6':'เสาร์',
    'อาทิตย์':'อาทิตย์','อา.':'อาทิตย์','sun':'อาทิตย์','sunday':'อาทิตย์','7':'อาทิตย์'
  };

  const normalizeDay=(d)=>{ if(!d) return null; const k=String(d).trim().toLowerCase(); return DAY_MAP[k]||d; };
  const esc=(s)=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'","&#039;");
  const typeClass=(t)=>{ const k=(t||'').toLowerCase(); if(k==='lab')return'tt-type-lab';
    if(k==='lecture')return'tt-type-lecture'; if(k==='tutorial')return'tt-type-tutorial';
    if(k==='seminar')return'tt-type-seminar'; return 'tt-type-default'; };
  const formatHH=(h)=>String(h).padStart(2,'0')+":00";

  const getHourRange=(r)=>{
    const toInt=v=>{ const n=parseInt(v,10); return Number.isFinite(n)?n:null; };
    let sh=null,eh=null;
    if(r.Hour_Start!=null) sh=toInt(r.Hour_Start);
    if(sh==null && r.Start_Hour!=null) sh=toInt(r.Start_Hour);
    if(sh==null && r.Hour!=null && r.Hour!=="") sh=toInt(r.Hour);
    if(r.Hour_End!=null) eh=toInt(r.Hour_End);
    if(eh==null && r.End_Hour!=null) eh=toInt(r.End_Hour);
    if(eh==null && sh!=null && r.Duration_Hours!=null) eh=sh+toInt(r.Duration_Hours);
    if(sh==null) return null; if(eh==null) eh=sh+1; return [sh,eh];
  };

  const getDay=(r)=>{ let day=null; if(r.Day) day=r.Day; else if(r.Time_Slot) day=String(r.Time_Slot).split('_')[0]; return normalizeDay(day); };

  // เปิดโมดัล + โหลดข้อมูล
  window.viewSchedule=function(){
    const modal=new bootstrap.Modal(document.getElementById("scheduleModal"));
    modal.show();
    selectedCategory=document.getElementById("ttCategory")?.value||"Teacher";
    selectedItem=""; searchTerm=""; viewMode="grid";

    document.getElementById("tt-select-view").classList.remove("d-none");
    document.getElementById("tt-table-view").classList.add("d-none");
    document.getElementById("tt-items-grid").innerHTML="";
    document.getElementById("tt-select-empty").classList.add("d-none");
    document.getElementById("tt-select-spinner").classList.remove("d-none");

    if(!SCHEDULES){
      fetch("/api/schedule/view/?order=day&dir=asc")
        .then(r=>r.json())
        .then(d=>{ SCHEDULES=(d && d.status==='success')?(d.schedules||[]):[]; })
        .catch(()=>{ SCHEDULES=[]; })
        .finally(()=>{ document.getElementById("tt-select-spinner").classList.add("d-none"); buildUniqueItems(); });
    }else{
      document.getElementById("tt-select-spinner").classList.add("d-none");
      buildUniqueItems();
    }
  };

  // สร้างรายการให้เลือก (อาจารย์/ห้อง/กลุ่ม)
  function buildUniqueItems(){
    const field=(selectedCategory==='Teacher')?'Teacher':(selectedCategory==='Room')?'Room':'Student_Group';
    const items=[...new Set((SCHEDULES||[]).map(x=>(x[field]||'').trim()).filter(Boolean))]
      .sort(new Intl.Collator('th').compare);

    const grid=document.getElementById("tt-items-grid");
    grid.innerHTML=items.map(name=>`
      <div class="col">
        <div class="card h-100 shadow-sm border-0 tt-item-card" data-name="${esc(name)}" role="button" tabindex="0">
          <div class="card-body text-center">
            <div class="mb-3">
              ${selectedCategory==='Teacher' ? '<i class="bi bi-person-circle fs-2 text-primary"></i>' :
                selectedCategory==='Room' ? '<i class="bi bi-geo-alt fs-2 text-success"></i>' :
                '<i class="bi bi-book fs-2 text-purple"></i>'}
            </div>
            <h6 class="fw-semibold mb-1">${esc(name)}</h6>
            <div class="text-muted small">คลิกเพื่อดูตารางสอน</div>
          </div>
        </div>
      </div>`).join("");

    document.getElementById("tt-select-empty").classList.toggle("d-none", items.length>0);

    document.querySelectorAll(".tt-item-card").forEach(el=>{
      const go=()=>{ selectedItem=el.dataset.name||""; enterTableView(); };
      el.addEventListener("click",go);
      el.addEventListener("keypress",(e)=>{ if(e.key==="Enter") go(); });
    });
  }

  document.getElementById("ttCategory")?.addEventListener("change",(e)=>{
    selectedCategory=e.target.value; selectedItem=""; buildUniqueItems();
  });

  function enterTableView(){
    document.getElementById("tt-select-view").classList.add("d-none");
    document.getElementById("tt-table-view").classList.remove("d-none");
    document.getElementById("tt-search").value=""; searchTerm=""; viewMode="grid";
    document.getElementById("tt-toggle-text").textContent="มุมมองรายการ";
    renderTableView();
  }

  document.getElementById("tt-back-btn")?.addEventListener("click",()=>{
    document.getElementById("tt-table-view").classList.add("d-none");
    document.getElementById("tt-select-view").classList.remove("d-none");
  });
  document.getElementById("tt-search")?.addEventListener("input",(e)=>{ searchTerm=e.target.value||""; renderTableView(); });
  document.getElementById("tt-toggle-view")?.addEventListener("click",()=>{
    viewMode=(viewMode==="grid")?"list":"grid";
    document.getElementById("tt-toggle-text").textContent=(viewMode==="grid")?"มุมมองรายการ":"มุมมองตาราง";
    renderTableView();
  });

  function renderTableView(){
    filtered=(SCHEDULES||[]).filter(x=>{
      const val=(selectedCategory==='Teacher')?(x.Teacher||''):(selectedCategory==='Room')?(x.Room||''):(x.Student_Group||'');
      return (val.trim()===selectedItem);
    });
    if(searchTerm){
      const q=searchTerm.toLowerCase();
      filtered=filtered.filter(x=>[x.Subject_Name,x.Course_Code,x.Teacher,x.Room]
        .some(s=>(String(s||'').toLowerCase()).includes(q)));
    }

    document.getElementById("tt-title").innerHTML=`ตารางสอน - ${esc(selectedItem)}`;
    const catLabel=(selectedCategory==='Teacher')?'อาจารย์':(selectedCategory==='Room')?'ห้อง':'กลุ่มนักศึกษา';
    document.getElementById("tt-desc").innerHTML=`ตารางเรียนของ${catLabel} ${esc(selectedItem)}`;

    if(viewMode==="grid"){
      document.getElementById("tt-grid-wrap").classList.remove("d-none");
      document.getElementById("tt-list-wrap").classList.add("d-none");
      renderGrid();
    }else{
      document.getElementById("tt-list-wrap").classList.remove("d-none");
      document.getElementById("tt-grid-wrap").classList.add("d-none");
      renderList();
    }
  }

  function renderList(){
    const grid=document.getElementById("tt-list-grid");
    if(!filtered.length){
      grid.innerHTML=""; document.getElementById("tt-list-empty").classList.remove("d-none"); return;
    }
    document.getElementById("tt-list-empty").classList.add("d-none");

    grid.innerHTML=filtered.map(item=>`
      <div class="col-12 col-md-6 col-xl-4">
        <div class="card h-100 shadow-sm border-0">
          <div class="card-body">
            <h6 class="fw-semibold mb-2">${esc(item.Subject_Name||'')}</h6>
            <p class="text-muted small mb-3">${esc(item.Course_Code||'')}</p>
            <div class="small"><i class="bi bi-calendar-week me-1"></i>${esc(item.Day||'')}</div>
            <div class="small"><i class="bi bi-clock me-1"></i>${esc(item.Time_Slot||(String(item.Hour||'')+':00'))}</div>
            <div class="small"><i class="bi bi-geo-alt me-1"></i>${esc(item.Room||'')}</div>
            <div class="small"><i class="bi bi-person me-1"></i>${esc(item.Teacher||'')}</div>
            <span class="badge bg-secondary mt-2">${esc(item.Type||'')}</span>
          </div>
        </div>
      </div>`).join("");
  }

  function mergeBlocks(rows){
    const byDay=Object.fromEntries(DAY_ORDER.map(d=>[d,{}]));
    for(const r of rows){
      const day=getDay(r); if(!day || !byDay[day]) continue;
      const key=[r.Course_Code||'',r.Subject_Name||'',r.Teacher||'',r.Room||'',(r.Type||'').toLowerCase()].join('|');
      byDay[day][key] ??= [];
      const hr=getHourRange(r); if(!hr) continue;
      let [sh,eh]=hr; if(eh<=sh) eh=sh+1;
      if(eh<START_HOUR || sh>END_HOUR) continue;
      sh=Math.max(sh,START_HOUR); eh=Math.min(eh,END_HOUR+1);
      byDay[day][key].push({startHour:sh,endHour:eh,
        Course_Code:r.Course_Code||'', Subject_Name:r.Subject_Name||'', Teacher:r.Teacher||'',
        Room:r.Room||'', Type:(r.Type||'').toLowerCase(), Day:day});
    }
    const blocks={};
    for(const day of Object.keys(byDay)){
      const merged=[];
      for(const key of Object.keys(byDay[day])){
        const xs=byDay[day][key].sort((a,b)=>a.startHour-b.startHour);
        let cur=null;
        for(const b of xs){
          if(!cur){ cur={...b}; continue; }
          if(b.startHour<=cur.endHour){ cur.endHour=Math.max(cur.endHour,b.endHour); }
          else{ merged.push(cur); cur={...b}; }
        }
        if(cur) merged.push(cur);
      }
      blocks[day]=merged;
    }
    return blocks;
  }

  function renderGrid(){
    const table=document.getElementById("tt-table");
    if(!filtered.length){
      table.innerHTML=""; document.getElementById("tt-grid-empty").classList.remove("d-none"); return;
    }
    document.getElementById("tt-grid-empty").classList.add("d-none");

    const blocksByDay=mergeBlocks(filtered);

    let thead='<thead><tr><th class="sticky-top text-center align-middle">วัน / เวลา</th>';
    for(let h=START_HOUR; h<=END_HOUR; h++) thead+=`<th class="sticky-top text-center">${formatHH(h)}</th>`;
    thead+='</tr></thead>';

    let tbody='<tbody>';
    for(const day of DAY_ORDER){
      const blocks=blocksByDay[day]||[];
      const startIndex=Object.fromEntries(blocks.map(b=>[String(b.startHour),b]));
      tbody+=`<tr><th class="sticky-col">${day}</th>`;
      for(let h=START_HOUR; h<=END_HOUR; h++){
        const b=startIndex[String(h)];
        if(b){
          const colspan=Math.max(1,b.endHour-b.startHour);
          const teacherShort=(b.Teacher||'').replace(/^อ\./,'');
          tbody+=`<td colspan="${colspan}">
            <div class="tt-slot ${typeClass(b.Type)}">
              <div class="fw-semibold small">${esc(b.Subject_Name||'-')}</div>
              <div class="small">${esc(b.Course_Code||'')}</div>
              <div class="small mt-1"><i class="bi bi-geo-alt me-1"></i>${esc(b.Room||'-')}
                <span class="ms-2"><i class="bi bi-person me-1"></i>${esc(teacherShort||'-')}</span></div>
              <span class="tt-badge text-white">${esc(b.Type||'—')}</span>
            </div>
          </td>`;
          h+=(colspan-1);
        }else{
          const inside=blocks.some(x=>x.startHour<h && x.endHour>h);
          if(!inside) tbody+=`<td>&nbsp;</td>`;
        }
      }
      tbody+=`</tr>`;
    }
    tbody+='</tbody>';
    table.innerHTML=thead+tbody;
  }
})();
