// static/js/generated.js

// ====== helper: toast ตามธีม (โทนเดียวกับ subject.js) ======
function showToast(kind, title, message) {
  const host = document.getElementById('toastHost');
  if (!host) return;
  const id = 'toast_' + Date.now();
  const bgMap = {
    success: 'bg-success text-white',
    warning: 'bg-warning',
    danger: 'bg-danger text-white',
    info: 'bg-info',
  };
  const cls = bgMap[kind] || 'bg-dark text-white';
  const el = document.createElement('div');
  el.className = 'toast align-items-center rounded-3 overflow-hidden';
  el.id = id;
  el.role = 'alert';
  el.ariaLive = 'assertive';
  el.ariaAtomic = 'true';
  el.innerHTML = `
    <div class="toast-header ${cls}">
      <strong class="me-auto">${title || ''}</strong>
      <button type="button" class="btn-close btn-close-white ms-2 mb-1" data-bs-dismiss="toast" aria-label="Close"></button>
    </div>
    <div class="toast-body">${message || ''}</div>
  `;
  host.appendChild(el);
  const t = new bootstrap.Toast(el, { delay: 2500 });
  t.show();
  el.addEventListener('hidden.bs.toast', () => el.remove());
}

// ====== fetch wrapper ======
async function apiGet(url) {
  const resp = await fetch(url, { headers: { 'Accept': 'application/json' } });
  if (!resp.ok) {
    const txt = await resp.text();
    throw new Error(txt || `HTTP ${resp.status}`);
  }
  return resp.json();
}

// ====== mapping day / time helper ======
function dayName(value) {
  // รองรับได้ทั้ง 0..6 หรือ 1..7
  const days0 = ['อา', 'จ', 'อ', 'พ', 'พฤ', 'ศ', 'ส'];
  const days1 = [null, 'จ', 'อ', 'พ', 'พฤ', 'ศ', 'ส', 'อา'];
  if (value === '' || value === null || value === undefined) return '-';
  const n = Number(value);
  if (Number.isNaN(n)) return String(value);
  // หากโมเดลเก็บ 0=อา
  if (n >= 0 && n <= 6) return days0[n];
  // หากโมเดลเก็บ 1=จันทร์
  if (n >= 1 && n <= 7) return days1[n] || '-';
  return '-';
}

function timeRange(startSlot, endSlot) {
  // ถ้าเก็บเป็น slot เป็นชั่วโมง เช่น 8..9 => 08:00-09:00
  if (startSlot === '' || startSlot === null || startSlot === undefined) return '-';
  const s = Number(startSlot), e = Number(endSlot);
  if (Number.isNaN(s)) return String(startSlot);
  const pad = (x) => String(x).padStart(2, '0');
  const fmt = (slot) => `${pad(slot)}:00`;
  return e ? `${fmt(s)}-${fmt(e)}` : `${fmt(s)}`;
}

// ====== render rows ======
function renderGenerated(rows) {
  const tb = document.getElementById('generatedTableBody');
  if (!tb) return;
  tb.innerHTML = '';
  if (!rows || rows.length === 0) {
    tb.innerHTML = `<tr><td colspan="7" class="text-center text-muted py-4">ยังไม่มีข้อมูลที่สร้าง</td></tr>`;
    return;
  }

  const frag = document.createDocumentFragment();
  rows.forEach((r) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td class="text-center">${dayName(r.day_of_week)}</td>
      <td class="text-center">${timeRange(r.start_slot, r.end_slot)}</td>
      <td class="text-center"><span class="fw-semibold">${r.subject_code || '-'}</span></td>
      <td>${r.subject_name || '-'}</td>
      <td>${r.teacher_name || '-'}</td>
      <td class="text-center">${r.room_name || '-'}</td>
      <td class="text-center">
        ${(r.student_group || '-')}${r.group_type ? ` / ${r.group_type}` : ''}
      </td>
    `;
    frag.appendChild(tr);
  });
  tb.appendChild(frag);
}

// ====== init ======
document.addEventListener('DOMContentLoaded', () => {
  const btn = document.getElementById('btnLoadGenerated');
  if (btn) {
    btn.addEventListener('click', async () => {
      try {
        const data = await apiGet('/api/generated/');
        renderGenerated(data.results || []);
        showToast('success', 'สำเร็จ', 'โหลดตารางที่สร้างแล้วเรียบร้อย');
      } catch (err) {
        console.error(err);
        showToast('danger', 'ผิดพลาด', 'ไม่สามารถโหลดข้อมูลได้');
      }
    });
  }
});
