/* ── State ── */
let role = null;
let sessionPatient = null;
let sessionDoctor  = null;
let currentDoctor  = null;
let currentPatient = null;
let _sessionToken  = '';

/* Save initial welcome HTML to restore on logout */
const _pWelcomeHTML = document.getElementById('p-messages').innerHTML;

/* ── Screen switching ── */
function show(id) {
  ['screen-login','screen-select-doctor','screen-patient','screen-doctor'].forEach(s => {
    document.getElementById(s).classList.toggle('hidden', s !== id);
  });
}

function enterRole(r) {
  role = r;
  if (r === 'patient') {
    show('screen-patient');
    document.getElementById('p-input').focus();
  } else {
    show('screen-select-doctor');
    loadPractitioners();
  }
}

// ── Login 2 bước ──
let _loginPhone = '';
let _loginData  = null;

function _backToStep1() {
  document.getElementById('login-step1').classList.remove('hidden');
  document.getElementById('login-step2').classList.add('hidden');
  document.getElementById('login-first-time')?.classList.add('hidden');
  document.getElementById('login-error').classList.add('hidden');
  document.getElementById('login-phone').focus();
}

async function _doCheckPhone() {
  const phone = document.getElementById('login-phone').value.trim();
  const errEl = document.getElementById('login-error');
  errEl.classList.add('hidden');
  if (!phone) { errEl.textContent = 'Vui lòng nhập số điện thoại.'; errEl.classList.remove('hidden'); return; }

  try {
    const res  = await fetch('/api/login', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ phone, password: '' }),
    });
    const data = await res.json();

    if (!res.ok) {
      errEl.textContent = data.detail || 'Không tìm thấy số điện thoại.';
      errEl.classList.remove('hidden'); return;
    }

    _loginPhone = phone;
    _loginData  = data;

    if (data.status === 'ok') {
      // Lần đầu — vào luôn
      _enterPortal(data);
    } else if (data.status === 'need_password') {
      // Đã có tài khoản — yêu cầu mật khẩu
      document.getElementById('login-step1').classList.add('hidden');
      document.getElementById('login-greeting').textContent = `Xin chào, ${data.name}!`;
      document.getElementById('login-step2').classList.remove('hidden');
      document.getElementById('login-password').value = '';
      document.getElementById('login-password').focus();
    }
  } catch(e) {
    errEl.textContent = 'Lỗi: ' + (e && e.message ? e.message : String(e));
    errEl.classList.remove('hidden');
    console.error('[login step1]', e);
  }
}

async function _doLoginStep2() {
  const password = document.getElementById('login-password').value;
  const errEl    = document.getElementById('login-error2');
  errEl.classList.add('hidden');
  if (!password) { errEl.textContent = 'Vui lòng nhập mật khẩu.'; errEl.classList.remove('hidden'); return; }

  try {
    const res  = await fetch('/api/login', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ phone: _loginPhone, password }),
    });
    const data = await res.json();
    if (!res.ok) {
      errEl.textContent = data.detail || 'Mật khẩu không đúng.';
      errEl.classList.remove('hidden'); return;
    }
    _enterPortal(data);
  } catch(e) {
    errEl.textContent = 'Lỗi: ' + (e && e.message ? e.message : String(e));
    errEl.classList.remove('hidden');
    console.error('[login]', e);
  }
}

function _enterAfterFirstLogin() {
  _enterPortal(_loginData);
}

function _enterPortal(data) {
  document.getElementById('login-phone').value = '';
  document.getElementById('login-step1').classList.remove('hidden');
  document.getElementById('login-step2').classList.add('hidden');
  document.getElementById('login-first-time')?.classList.add('hidden');
  _sessionToken = data.token || '';
  if (data.role === 'doctor') {
    role = 'doctor';
    currentDoctor = { id: data.id, name: data.name };
    show('screen-doctor');
    _initDoctorSession();
    _startPendingPoll();
  } else {
    role = 'patient';
    currentPatient = data.id ? { id: data.id, name: data.name } : null;
    document.getElementById('btn-my-profile').style.display = currentPatient ? '' : 'none';
    show('screen-patient');
    document.getElementById('p-input').focus();
    if (currentPatient) _triggerPatientInit();
  }
}

function _initDoctorSession() {
  if (currentDoctor) {
    const nameEl = document.getElementById('doc-name');
    if (nameEl) nameEl.textContent = currentDoctor.name || '';
  }
}

function _enterAsGuest() {
  role = 'patient';
  show('screen-patient');
  document.getElementById('p-input').focus();
}

// Enter key để submit login
document.addEventListener('keydown', function(e) {
  if (e.key !== 'Enter') return;
  const step1 = document.getElementById('login-step1');
  const step2 = document.getElementById('login-step2');
  if (step1 && !step1.classList.contains('hidden')) _doCheckPhone();
  else if (step2 && !step2.classList.contains('hidden')) _doLoginStep2();
});

function logout() {
  role = null;
  currentDoctor  = null;
  currentPatient = null;
  _sessionToken  = '';
  _resetDocChatUI();
  _stopPendingPoll();
  sessionPatient = null;
  document.getElementById('btn-my-profile').style.display = 'none';
  document.getElementById('p-messages').innerHTML = _pWelcomeHTML;
  show('screen-login');
}

/* ── Practitioner selection ── */
let _allPractitioners = [];

function _practInitials(name) {
  const clean = (name || '').replace(/^BS\.\s*/i, '').trim();
  const words = clean.split(/\s+/).filter(Boolean);
  if (words.length >= 2) return (words[0][0] + words[words.length - 1][0]).toUpperCase();
  return clean.slice(0, 2).toUpperCase();
}

function _avatarColor(name) {
  const colors = ['#005d5d','#0043ce','#6929c4','#9f1853','#198038','#b28600','#00539a'];
  let h = 0;
  for (const c of (name || '')) h = (h * 31 + c.charCodeAt(0)) & 0xffff;
  return colors[h % colors.length];
}

function _renderPractCard(p) {
  const initials = _practInitials(p.name);
  const color    = _avatarColor(p.name);
  return `
    <div class="pract-card" onclick="selectDoctor('${p.id}','${(p.name||'').replace(/'/g,'&#39;')}')">
      <div class="p-avatar" style="background:${color}">${initials}</div>
      <div class="p-name">${p.name || '(Chưa có tên)'}</div>
      <div class="p-spec">${p.specialty || ''}</div>
      <button class="p-btn">Chọn →</button>
    </div>`;
}

function filterPractitioners(q) {
  const grid = document.getElementById('pract-grid');
  const list = q.trim()
    ? _allPractitioners.filter(p => (p.name||'').toLowerCase().includes(q.toLowerCase()))
    : _allPractitioners;
  grid.innerHTML = list.length
    ? list.map(_renderPractCard).join('')
    : '<p style="color:var(--text-02);font-size:13px">Không tìm thấy bác sĩ nào.</p>';
}

async function loadPractitioners() {
  const grid = document.getElementById('pract-grid');
  grid.innerHTML = [0,1,2,3].map(() => `
    <div class="pract-card" style="pointer-events:none">
      <div style="background:var(--ui-03);border-radius:50%;width:52px;height:52px;margin-bottom:12px;animation:pulse 1.2s infinite"></div>
      <div style="background:var(--ui-03);height:14px;width:70%;border-radius:2px;margin-bottom:8px;animation:pulse 1.2s infinite"></div>
      <div style="background:var(--ui-03);height:12px;width:50%;border-radius:2px;margin-bottom:14px;animation:pulse 1.2s infinite"></div>
      <div style="background:var(--ui-03);height:28px;border-radius:2px;animation:pulse 1.2s infinite"></div>
    </div>`).join('');
  try {
    const data = await fetch('/api/practitioners').then(r => r.json());
    _allPractitioners = data.practitioners || [];
    if (!_allPractitioners.length) {
      grid.innerHTML = '<p style="color:var(--text-02);padding:16px">Không tìm thấy bác sĩ nào trong hệ thống.</p>';
      return;
    }
    grid.innerHTML = _allPractitioners.map(_renderPractCard).join('');
  } catch (e) {
    grid.innerHTML = `<p style="color:var(--danger);padding:16px">Lỗi tải danh sách: ${e.message}</p>`;
  }
}

async function selectDoctor(id, name) {
  currentDoctor = { id, name };
  document.getElementById('doctor-name-display').textContent = name;
  _resetDocChatUI();
  show('screen-doctor');
  docNav('dashboard');
  document.getElementById('d-input').focus();
  _startPendingPoll();

  // Khôi phục hội thoại gần nhất
  try {
    const res = await fetch(`/session/doctor/${id}/current`);
    const data = await res.json();
    sessionDoctor = data.session_id;
    if (data.messages && data.messages.length > 0) {
      const msgsEl = document.getElementById('d-messages');
      document.getElementById('d-welcome')?.remove();
      for (const m of data.messages) {
        const isUser = m.role === 'user';
        const div = document.createElement('div');
        div.className = `msg-row ${isUser ? 'user' : 'bot'}`;
        const av = document.createElement('div');
        av.className = `avatar ${isUser ? 'user' : 'bot'}`;
        av.textContent = isUser ? 'BS' : 'AI';
        const bub = document.createElement('div');
        bub.className = 'bubble';
        bub.innerHTML = isUser ? m.content : marked.parse(m.content);
        div.appendChild(av); div.appendChild(bub);
        msgsEl.appendChild(div);
      }
      msgsEl.scrollTop = msgsEl.scrollHeight;
    }
  } catch(e) { /* bình thường nếu chưa có session */ }
}

/* ── Doctor nav ── */
const NAV_TITLES = {
  dashboard: 'Dashboard', appointments: 'Lịch hẹn hôm nay',
  patients: 'Bệnh nhân', lab: 'Xét nghiệm', search: 'Tra cứu hồ sơ'
};
const NAV_PLACEHOLDERS = {
  dashboard:    'Hỏi về lịch hẹn, bệnh nhân, tình trạng phòng khám...',
  appointments: 'Tìm lịch hẹn theo tên bệnh nhân hoặc khoa...',
  patients:     'Nhập tên bệnh nhân để tra cứu hồ sơ...',
  lab:          'Hỏi về kết quả xét nghiệm của bệnh nhân...',
  search:       'Nhập tên bệnh nhân, ngày sinh hoặc SĐT để tìm hồ sơ...',
};

function docNav(nav) {
  document.querySelectorAll('.doc-nav-item').forEach(el => el.classList.remove('active'));
  document.getElementById('nav-' + nav)?.classList.add('active');
  document.getElementById('doc-page-title').textContent = NAV_TITLES[nav] || nav;
  document.getElementById('d-input').placeholder = NAV_PLACEHOLDERS[nav] || 'Nhập câu hỏi...';
  renderDocContent(nav);
}

/* ── Skeleton / loading HTML ── */
function skeletonRows(cols, rows = 4) {
  const cells = Array(cols).fill('<td><span style="display:inline-block;width:80%;height:12px;background:var(--ui-03);border-radius:2px;animation:pulse 1.2s infinite"></span></td>').join('');
  return Array(rows).fill(`<tr>${cells}</tr>`).join('');
}

function renderDocContent(nav) {
  const el = document.getElementById('doc-content');

  if (nav === 'dashboard') {
    el.innerHTML = `
      <div class="stat-cards">
        <div class="stat-card">
          <div class="s-label">📅 Lịch hẹn hôm nay</div>
          <div class="s-value" id="stat-appointments">--</div>
          <div class="s-sub">Lịch đã đặt</div>
        </div>
        <div class="stat-card">
          <div class="s-label">⏳ Đang chờ khám</div>
          <div class="s-value" id="stat-waiting">--</div>
          <div class="s-sub">Bệnh nhân</div>
        </div>
        <div class="stat-card">
          <div class="s-label">👥 Tổng bệnh nhân</div>
          <div class="s-value" id="stat-total">--</div>
          <div class="s-sub">Trong hệ thống</div>
        </div>
      </div>
      <div class="chart-row">
        <div class="chart-card">
          <div class="c-label">Lịch hẹn 7 ngày tới</div>
          <div class="chart-wrap"><canvas id="chart-bar"></canvas></div>
        </div>
        <div class="chart-card">
          <div class="c-label">Phân bố trạng thái</div>
          <div class="chart-wrap"><canvas id="chart-donut"></canvas></div>
        </div>
      </div>`;
    loadDashboardStats();

  } else if (nav === 'appointments') {
    const today = new Date().toISOString().slice(0, 10);
    el.innerHTML = `
      <div class="page-toolbar">
        <input type="date" id="appt-date" class="tb-search" style="max-width:160px"
          value="${today}" onchange="loadAppointments()">
        <button class="tb-btn" style="background:var(--ui-02);color:var(--brand-01);border:1px solid var(--brand-01);padding:6px 10px;"
          onclick="document.getElementById('appt-date').value='${today}';loadAppointments()">Hôm nay</button>
        <input id="appt-search" class="tb-search" placeholder="🔍  Lọc theo tên bệnh nhân..."
          oninput="filterAppointments()">
        <select id="appt-status" class="tb-select" onchange="filterAppointments()">
          <option value="">Tất cả trạng thái</option>
          <option value="booked">Đã xác nhận</option>
          <option value="fulfilled">Đã khám</option>
          <option value="cancelled">Đã hủy</option>
          <option value="noshow">Vắng mặt</option>
        </select>
        <button class="tb-btn" onclick="loadAppointments()">↺ Làm mới</button>
      </div>
      <div class="data-table-wrap">
        <table class="data-table">
          <thead><tr><th>Giờ</th><th>Bệnh nhân</th><th>Khoa</th>
            <th>Bác sĩ</th><th>Trạng thái</th><th>Lý do</th><th>Hành động</th></tr></thead>
          <tbody id="appt-tbody">${skeletonRows(6)}</tbody>
        </table>
      </div>`;
    loadAppointments();

  } else if (nav === 'patients') {
    el.innerHTML = `
      <div class="pt-tabs">
        <button class="pt-tab active" id="pt-tab-mine" onclick="switchPatientTab('mine')">👤 Bệnh nhân của tôi</button>
        <button class="pt-tab" id="pt-tab-all" onclick="switchPatientTab('all')">👥 Tất cả bệnh nhân</button>
      </div>
      <div id="pt-mine-panel">
        <div class="data-table-wrap">
          <table class="data-table">
            <thead><tr><th>Họ tên</th><th>Giới tính / Ngày sinh</th><th>SĐT</th>
              <th>PLT (K/μL)</th><th>Khám gần nhất</th><th>Hành động</th></tr></thead>
            <tbody id="pt-mine-tbody">${skeletonRows(6)}</tbody>
          </table>
        </div>
      </div>
      <div id="pt-all-panel" class="hidden">
        <div class="page-toolbar" style="margin-top:0">
          <input id="pt-search" class="tb-search" placeholder="🔍  Tìm theo tên bệnh nhân..."
            onkeydown="if(event.key==='Enter') loadPatients()">
          <button class="tb-btn" onclick="loadPatients()">Tìm kiếm</button>
          <button class="tb-btn" style="background:var(--ui-02);color:var(--brand-01);border:1px solid var(--brand-01);"
            onclick="loadPatients('')">Tất cả</button>
        </div>
        <div class="data-table-wrap">
          <table class="data-table">
            <thead><tr><th>Họ tên</th><th>Ngày sinh</th><th>Giới tính</th>
              <th>SĐT</th><th>Hành động</th></tr></thead>
            <tbody id="pt-tbody">${skeletonRows(5)}</tbody>
          </table>
        </div>
      </div>`;
    loadMyPatients();

  } else if (nav === 'lab') {
    el.innerHTML = `
      <div class="page-toolbar">
        <select id="lab-cat" class="tb-select" onchange="loadObservations()">
          <option value="all">Tất cả loại</option>
          <option value="vital-signs">Sinh hiệu</option>
          <option value="laboratory">Xét nghiệm</option>
        </select>
        <button class="tb-btn" onclick="loadObservations()">↺ Làm mới</button>
        <button class="tb-btn tb-btn-primary" onclick="openLabCbcPicker()" style="margin-left:auto">+ Nhập CBC</button>
      </div>
      <div id="lab-cbc-picker" class="hidden" style="background:var(--ui-02);border:1px solid var(--ui-03);border-radius:6px;padding:12px 16px;margin-bottom:12px">
        <div style="font-size:13px;font-weight:600;margin-bottom:8px;color:var(--text-01)">Chọn bệnh nhân để nhập CBC</div>
        <div style="display:flex;gap:8px;margin-bottom:8px">
          <input id="lab-cbc-search" class="srch-input" placeholder="Nhập tên bệnh nhân…"
            oninput="searchLabCbcPatient()" style="flex:1">
          <button class="tb-btn" onclick="closeLabCbcPicker()">✕</button>
        </div>
        <div id="lab-cbc-results"></div>
      </div>
      <div class="data-table-wrap">
        <table class="data-table">
          <thead><tr><th>Bệnh nhân</th><th>Chỉ số</th><th>Giá trị</th>
            <th>Trạng thái</th><th>Ngày</th></tr></thead>
          <tbody id="lab-tbody">${skeletonRows(5)}</tbody>
        </table>
      </div>`;
    loadObservations();

  } else if (nav === 'search') {
    el.innerHTML = `
      <div class="search-hero">
        <label>Tìm kiếm hồ sơ bệnh nhân</label>
        <div class="search-hero-row">
          <input id="search-input" placeholder="Nhập họ tên bệnh nhân..."
            onkeydown="if(event.key==='Enter') searchPatientAI()">
          <button class="tb-btn" onclick="searchPatientAI()">Tìm kiếm (AI)</button>
        </div>
        <div class="search-hero-hint">Trợ lý AI sẽ tìm và hiển thị hồ sơ bên dưới.</div>
      </div>`;
  }
}

/* ─── FHIR Data Loaders ─── */

window._apptData = [];  // cache for client-side filter

const STATUS_VI = {
  booked: ['badge-green', 'Đã xác nhận'],
  fulfilled: ['badge-gray', 'Đã khám'],
  cancelled: ['badge-red', 'Đã hủy'],
  noshow: ['badge-yellow', 'Vắng mặt'],
  pending: ['badge-yellow', 'Chờ xác nhận'],
};
function statusBadge(s) {
  const [cls, label] = STATUS_VI[s] || ['badge-gray', s];
  return `<span class="badge ${cls}">${label}</span>`;
}

let _barChart = null, _donutChart = null;

async function loadDashboardStats() {
  try {
    const today   = new Date();
    const d_from  = today.toISOString().slice(0, 10);
    const d_to    = new Date(today.getTime() + 6 * 86400000).toISOString().slice(0, 10);
    const pId     = currentDoctor ? '&practitioner_id=' + currentDoctor.id : '';
    const rangeUrl = `/api/appointments?date_from=${d_from}&date_to=${d_to}${pId}`;

    const [rangeRes, ptRes] = await Promise.all([
      fetch(rangeUrl).then(r => r.json()),
      fetch('/api/patients?_count=1').then(r => r.json()),
    ]);

    const allAppts = rangeRes.appointments || [];

    // ── Stat cards ──
    const todayAppts = allAppts.filter(a => a.start.startsWith(d_from));
    const waiting    = todayAppts.filter(a => a.status === 'booked').length;
    document.getElementById('stat-appointments').textContent = todayAppts.length;
    document.getElementById('stat-waiting').textContent      = waiting;
    document.getElementById('stat-total').textContent        = ptRes.total ?? '--';

    // ── Bar chart: lịch hẹn theo từng ngày ──
    const DAY_VI = ['CN', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7'];
    const labels = [], counts = [];
    for (let i = 0; i < 7; i++) {
      const d    = new Date(today.getTime() + i * 86400000);
      const dStr = d.toISOString().slice(0, 10);
      labels.push((i === 0 ? 'Hôm nay' : DAY_VI[d.getDay()]) + '\n' + dStr.slice(5).replace('-', '/'));
      counts.push(allAppts.filter(a => a.start.startsWith(dStr)).length);
    }

    // ── Donut chart: phân bố trạng thái ──
    const STATUS_LABEL = { booked: 'Đã xác nhận', fulfilled: 'Đã khám', cancelled: 'Đã hủy', noshow: 'Vắng mặt', pending: 'Chờ xác nhận' };
    const STATUS_COLOR = { booked: '#198038', fulfilled: '#8d8d8d', cancelled: '#da1e28', noshow: '#b28600', pending: '#0f62fe' };
    const statusCount  = {};
    allAppts.forEach(a => { statusCount[a.status] = (statusCount[a.status] || 0) + 1; });
    const dLabels = Object.keys(statusCount).map(s => STATUS_LABEL[s] || s);
    const dData   = Object.values(statusCount);
    const dColors = Object.keys(statusCount).map(s => STATUS_COLOR[s] || '#c6c6c6');

    // Destroy existing charts before re-render
    _barChart?.destroy();   _donutChart?.destroy();

    const barCtx    = document.getElementById('chart-bar')?.getContext('2d');
    const donutCtx  = document.getElementById('chart-donut')?.getContext('2d');
    if (!barCtx || !donutCtx) return;

    _barChart = new Chart(barCtx, {
      type: 'bar',
      data: {
        labels,
        datasets: [{
          data: counts,
          backgroundColor: labels.map((_, i) => i === 0 ? '#005d5d' : '#a3d4d2'),
          borderRadius: 2, borderSkipped: false,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          y: { beginAtZero: true, ticks: { stepSize: 1, font: { size: 11 } }, grid: { color: '#e0e0e0' } },
          x: { ticks: { font: { size: 10 } }, grid: { display: false } },
        },
      },
    });

    _donutChart = new Chart(donutCtx, {
      type: 'doughnut',
      data: { labels: dLabels, datasets: [{ data: dData, backgroundColor: dColors, borderWidth: 2, borderColor: '#fff' }] },
      options: {
        responsive: true, maintainAspectRatio: false,
        cutout: '62%',
        plugins: {
          legend: { position: 'right', labels: { font: { size: 11 }, boxWidth: 12, padding: 10 } },
        },
      },
    });

  } catch { /* silently keep -- */ }
}

async function loadAppointments() {
  const tbody = document.getElementById('appt-tbody');
  if (!tbody) return;
  tbody.innerHTML = skeletonRows(6);
  try {
    const date = document.getElementById('appt-date')?.value || '';
    const params = new URLSearchParams();
    if (date) params.set('date_str', date);
    if (currentDoctor) params.set('practitioner_id', currentDoctor.id);
    const apptUrl = '/api/appointments' + (params.toString() ? '?' + params.toString() : '');
    const data = await fetch(apptUrl).then(r => r.json());
    window._apptData = data.appointments || [];
    renderAppointmentRows(window._apptData);
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;color:var(--danger);padding:16px">Lỗi tải dữ liệu: ${e.message}</td></tr>`;
  }
}

function renderAppointmentRows(rows) {
  const tbody = document.getElementById('appt-tbody');
  if (!tbody) return;
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-03);padding:20px">Không có lịch hẹn</td></tr>';
    return;
  }
  tbody.innerHTML = rows.map(a => {
    const safeId = (a.id || '').replace(/'/g, '');
    const safePid  = (a.patient_id || '').replace(/'/g, '');
    const safePname = (a.patient_name || '').replace(/'/g, '').replace(/"/g, '');
    const actions = (a.status === 'proposed' || a.status === 'PROPOSED')
      ? `<button class="pending-confirm-btn" style="padding:4px 10px;font-size:12px;" onclick="confirmAppointment('${safeId}', this)">✓ Duyệt</button>
         <button class="pending-reject-btn"  style="padding:4px 10px;font-size:12px;margin-left:4px;" onclick="rejectAppointment('${safeId}', this)">✗ Từ chối</button>`
      : (a.status === 'booked')
      ? `<div style="display:flex;gap:4px;white-space:nowrap">
           <button class="pending-confirm-btn" style="padding:3px 8px;font-size:11px" onclick="openCompleteModal('${safeId}','${safePid}','${safePname}')">✓ Kết thúc</button>
           <button class="tb-btn" style="padding:3px 8px;font-size:11px" onclick="openApptDetail('${safeId}')">Chi tiết</button>
         </div>`
      : `<button class="tb-btn" style="padding:4px 10px;font-size:12px;" onclick="openApptDetail('${safeId}')">Chi tiết</button>`;
    return `<tr>
      <td>${a.start ? a.start.slice(11,16) : '--'}</td>
      <td>${a.patient_name || '—'}</td>
      <td>${a.department || '—'}</td>
      <td>${a.practitioner || '—'}</td>
      <td>${statusBadge(a.status)}</td>
      <td style="color:var(--text-02)">${a.reason || ''}</td>
      <td>${actions}</td>
    </tr>`;
  }).join('');
}

function filterAppointments() {
  const q   = (document.getElementById('appt-search')?.value || '').toLowerCase();
  const st  = document.getElementById('appt-status')?.value || '';
  const filtered = window._apptData.filter(a =>
    (!q  || a.patient_name.toLowerCase().includes(q)) &&
    (!st || a.status === st)
  );
  renderAppointmentRows(filtered);
}

async function loadPatients(q) {
  const tbody = document.getElementById('pt-tbody');
  if (!tbody) return;
  tbody.innerHTML = skeletonRows(5);
  const search = q !== undefined ? q : (document.getElementById('pt-search')?.value || '');
  try {
    const data = await fetch(`/api/patients?_count=30${search ? '&q=' + encodeURIComponent(search) : ''}`).then(r => r.json());
    const rows = data.patients || [];
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-03);padding:20px">Không tìm thấy bệnh nhân</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map(p => `
      <tr>
        <td><strong style="color:var(--brand-01)">${p.name || '—'}</strong></td>
        <td>${p.birth_date ? p.birth_date.split('-').reverse().join('/') : '—'}</td>
        <td>${p.gender || '—'}</td>
        <td>${p.phone || '—'}</td>
        <td><button class="tb-btn" style="padding:4px 10px;font-size:12px;"
            onclick="openPatientPanel('${p.id}')">Xem hồ sơ</button></td>
      </tr>`).join('');
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;color:var(--danger);padding:16px">Lỗi: ${e.message}</td></tr>`;
  }
}

function switchPatientTab(tab) {
  const isMine = tab === 'mine';
  document.getElementById('pt-tab-mine').classList.toggle('active', isMine);
  document.getElementById('pt-tab-all').classList.toggle('active', !isMine);
  document.getElementById('pt-mine-panel').classList.toggle('hidden', !isMine);
  document.getElementById('pt-all-panel').classList.toggle('hidden', isMine);
  if (!isMine && !document.getElementById('pt-tbody').children.length) loadPatients();
}

async function loadMyPatients() {
  const tbody = document.getElementById('pt-mine-tbody');
  if (!tbody) return;
  tbody.innerHTML = skeletonRows(6);
  if (!currentDoctor?.id) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-03);padding:20px">Không xác định được bác sĩ</td></tr>';
    return;
  }
  try {
    const data = await fetch(`/api/doctor/${currentDoctor.id}/patients`).then(r => r.json());
    const rows = data.patients || [];
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-03);padding:24px">Chưa có bệnh nhân nào</td></tr>';
      return;
    }
    const PLT_STYLE = {
      critical: 'color:#da1e28;font-weight:700',
      warning:  'color:#f1a10d;font-weight:700',
      normal:   'color:#24a148;font-weight:600',
      none:     'color:var(--text-03)',
    };
    const PLT_ICON = { critical: '🔴', warning: '⚠️', normal: '✅', none: '—' };
    tbody.innerHTML = rows.map(p => {
      const pltStyle = PLT_STYLE[p.plt_status] || '';
      const pltIcon  = PLT_ICON[p.plt_status] || '—';
      const birth = p.birth_date ? p.birth_date.split('-').reverse().join('/') : '—';
      const lastVisit = p.last_visit ? p.last_visit.split('-').reverse().join('/') : '—';
      return `<tr>
        <td><strong style="color:var(--brand-01)">${p.name || '—'}</strong></td>
        <td>${p.gender || '—'} · ${birth}</td>
        <td>${p.phone || '—'}</td>
        <td><span style="${pltStyle}">${pltIcon} ${p.plt_display}</span></td>
        <td>${lastVisit}</td>
        <td><button class="tb-btn" style="padding:4px 10px;font-size:12px;"
            onclick="openPatientPanel('${p.id}')">Xem hồ sơ</button></td>
      </tr>`;
    }).join('');
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;color:var(--danger);padding:16px">Lỗi: ${e.message}</td></tr>`;
  }
}

async function loadObservations() {
  const tbody = document.getElementById('lab-tbody');
  if (!tbody) return;
  tbody.innerHTML = skeletonRows(5);
  const cat = document.getElementById('lab-cat')?.value || 'all';
  try {
    const data = await fetch(`/api/observations?category=${cat}&_count=30`).then(r => r.json());
    const rows = data.observations || [];
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-03);padding:20px">Không có dữ liệu</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map(o => `
      <tr>
        <td>${o.patient_name || '—'}</td>
        <td>${o.name || '—'}</td>
        <td><strong>${o.value || '—'}</strong> <span style="color:var(--text-03)">${o.unit}</span></td>
        <td>${statusBadge(o.status)}</td>
        <td>${o.date || '—'}</td>
      </tr>`).join('');
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;color:var(--danger);padding:16px">Lỗi: ${e.message}</td></tr>`;
  }
}

function searchPatientAI() {
  const q = document.getElementById('search-input')?.value?.trim();
  if (q) fillD('Tìm hồ sơ bệnh nhân: ' + q);
}

/* ── Input helpers ── */
function setupInput(el, sendFn) {
  el.addEventListener('input', () => {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 120) + 'px';
  });
  el.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendFn(); }
  });
}

const pInput = document.getElementById('p-input');
const dInput = document.getElementById('d-input');
setupInput(pInput, () => sendMsg('patient'));
setupInput(dInput, () => sendMsg('doctor'));

function fillP(text) { pInput.value = text; pInput.focus(); pInput.dispatchEvent(new Event('input')); }
function fillD(text) { dInput.value = text; dInput.focus(); dInput.dispatchEvent(new Event('input')); }

/* ── Clear doctor chat ── */
function _resetDocChatUI() {
  sessionDoctor = null;
  document.getElementById('d-messages').innerHTML = `
    <div class="welcome" id="d-welcome" style="padding:32px 16px;">
      <div class="welcome-icon" style="width:48px;height:48px;font-size:20px;">🤖</div>
      <h2 style="font-size:16px;">Trợ lý dành cho bác sĩ</h2>
      <p style="font-size:13px;">Tra cứu hồ sơ, xem xét nghiệm, kiểm tra lịch hẹn bệnh nhân.</p>
    </div>`;
}

function clearDocChat() {
  newConversation();
}

/* ── History panel ── */
function openHistory() {
  document.getElementById('hist-sidebar').classList.add('open');
  histShowConversations();
}

function closeHistory() {
  document.getElementById('hist-sidebar').classList.remove('open');
}

function toggleHistory() {
  const sb = document.getElementById('hist-sidebar');
  if (sb.classList.contains('open')) { closeHistory(); }
  else { openHistory(); }
}

function newConversation() {
  if (!currentDoctor) return;
  _resetDocChatUI();
  sessionDoctor = `doctor_${currentDoctor.id}_${_genUUID()}`;
  closeHistory();
  _triggerDoctorInit();
}

async function _triggerDoctorInit() {
  const ctx = getCtx('doctor');
  const bub = createBotBubble(ctx);
  bub.textContent = '...';
  try {
    const res = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message:     '__init__',
        role:        'doctor',
        doctor_id:   currentDoctor.id,
        doctor_name: currentDoctor.name,
        session_id:  sessionDoctor,
      }),
    });
    const data = await res.json();
    if (data.session_id) sessionDoctor = data.session_id;
    bub.innerHTML = marked.parse(data.reply || '');
  } catch (e) {
    bub.textContent = 'Xin chào! Tôi có thể giúp gì cho bạn hôm nay?';
  }
}

async function _triggerPatientInit() {
  if (!currentPatient) return;
  const ctx = getCtx('patient');
  const bub = createBotBubble(ctx);
  bub.textContent = '...';
  try {
    const sid = sessionPatient || '';
    const res = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'x-session-token': _sessionToken },
      body: JSON.stringify({
        message:    '__init__',
        role:       'patient',
        session_id: sid,
      }),
    });
    const data = await res.json();
    if (data.session_id) sessionPatient = data.session_id;
    bub.innerHTML = marked.parse(data.reply || '');
  } catch (e) {
    bub.textContent = 'Xin chào! Tôi có thể giúp gì cho bạn hôm nay?';
  }
}

function _genUUID() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
    const r = Math.random() * 16 | 0;
    return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
  });
}

function _convDateLabel(updatedAt) {
  if (!updatedAt) return '';
  try {
    const d = new Date(updatedAt);
    const now = new Date();
    const diffMs = now - d;
    const diffDays = Math.floor(diffMs / 86400000);
    if (diffDays === 0) return 'Hôm nay';
    if (diffDays === 1) return 'Hôm qua';
    if (diffDays <= 7) return '7 ngày trước';
    if (diffDays <= 30) return '30 ngày trước';
    return 'Cũ hơn';
  } catch(e) { return ''; }
}

async function histShowConversations() {
  if (!currentDoctor) return;
  const content = document.getElementById('hist-content');
  content.innerHTML = '<p style="color:var(--text-02);font-size:13px;padding:4px 8px">Đang tải...</p>';
  try {
    const data = await fetch(`/session/doctor/${currentDoctor.id}/conversations`).then(r => r.json());
    const convs = data.conversations || [];
    if (!convs.length) {
      content.innerHTML = '<p style="color:var(--text-02);font-size:13px;text-align:center;padding-top:32px">Chưa có lịch sử hội thoại</p>';
      return;
    }

    const groupOrder = ['Hôm nay', 'Hôm qua', '7 ngày trước', '30 ngày trước', 'Cũ hơn'];
    const groups = {};
    for (const c of convs) {
      const g = _convDateLabel(c.updated_at) || 'Cũ hơn';
      (groups[g] = groups[g] || []).push(c);
    }

    let html = '';
    for (const g of groupOrder) {
      if (!groups[g]) continue;
      html += `<div style="font-size:11px;font-weight:600;color:var(--text-03);text-transform:uppercase;letter-spacing:0.5px;padding:10px 8px 4px">${g}</div>`;
      for (const c of groups[g]) {
        const isActive = sessionDoctor === c.session_id;
        html += `
        <div class="hist-conv-item${isActive ? ' active' : ''}"
             onclick="switchToConv('${c.session_id}', '${c.conv_id}')"
             data-conv="${c.conv_id}"
             style="padding:9px 10px;border-radius:6px;cursor:pointer;display:flex;align-items:center;gap:6px;margin-bottom:1px;${isActive ? 'background:var(--ui-04)' : ''}">
          <div style="flex:1;min-width:0">
            <div style="font-size:13px;color:var(--text-01);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${c.title}</div>
            <div style="font-size:11px;color:var(--text-03);margin-top:1px">${c.message_count} tin nhắn</div>
          </div>
          <button onclick="event.stopPropagation();deleteConv('${c.conv_id}')"
            style="opacity:0;flex-shrink:0;background:none;border:none;cursor:pointer;color:var(--text-03);font-size:15px;padding:2px 4px;border-radius:4px;transition:opacity 0.15s"
            class="hist-del-btn">×</button>
        </div>`;
      }
    }
    content.innerHTML = html;
  } catch(e) {
    content.innerHTML = `<p style="color:var(--danger);font-size:13px">Lỗi: ${e.message}</p>`;
  }
}

async function switchToConv(sessionId, convId) {
  if (!currentDoctor) return;
  closeHistory();
  try {
    const data = await fetch(`/session/doctor/${currentDoctor.id}/conversation/${convId}`).then(r => r.json());
    const msgs = data.messages || [];
    sessionDoctor = sessionId;
    const msgsEl = document.getElementById('d-messages');
    msgsEl.innerHTML = '';
    if (!msgs.length) {
      msgsEl.innerHTML = '<div class="welcome" id="d-welcome" style="padding:32px 16px;"><div class="welcome-icon" style="width:48px;height:48px;font-size:20px;">🤖</div><h2 style="font-size:16px;">Trợ lý dành cho bác sĩ</h2></div>';
      return;
    }
    for (const m of msgs) {
      const isUser = m.role === 'user';
      const div = document.createElement('div');
      div.className = `msg-row ${isUser ? 'user' : 'bot'}`;
      const av = document.createElement('div');
      av.className = `avatar ${isUser ? 'user' : 'bot'}`;
      av.textContent = isUser ? 'BS' : 'AI';
      const bub = document.createElement('div');
      bub.className = 'bubble';
      bub.innerHTML = isUser ? m.content : marked.parse(m.content);
      div.appendChild(av); div.appendChild(bub);
      msgsEl.appendChild(div);
    }
    msgsEl.scrollTop = msgsEl.scrollHeight;
  } catch(e) { console.error(e); }
}

async function deleteConv(convId) {
  if (!currentDoctor) return;
  await fetch(`/session/doctor/${currentDoctor.id}/conversation/${convId}`, {method: 'DELETE'});
  if (sessionDoctor === `doctor_${currentDoctor.id}_${convId}`) {
    sessionDoctor = `doctor_${currentDoctor.id}_${_genUUID()}`;
    _resetDocChatUI();
  }
  histShowConversations();
}

/* ── Shared chat logic ── */
function getCtx(role) {
  return role === 'patient'
    ? { msgsEl: document.getElementById('p-messages'),
        inputEl: pInput,
        sendEl:  document.getElementById('p-send'),
        welcomeId: 'p-welcome',
        session: sessionPatient,
        setSession: s => { sessionPatient = s; } }
    : { msgsEl: document.getElementById('d-messages'),
        inputEl: dInput,
        sendEl:  document.getElementById('d-send'),
        welcomeId: 'd-welcome',
        session: sessionDoctor,
        setSession: s => { sessionDoctor = s; } };
}

function _fmtTime() {
  const n = new Date();
  return n.getHours().toString().padStart(2,'0') + ':' + n.getMinutes().toString().padStart(2,'0');
}

function _addMeta(row, time, copyText) {
  const meta = document.createElement('div');
  meta.className = 'msg-meta';
  if (copyText !== undefined) {
    const btn = document.createElement('button');
    btn.className = 'copy-btn'; btn.textContent = 'Sao chép';
    btn.onclick = () => {
      navigator.clipboard.writeText(copyText).then(() => {
        btn.textContent = 'Đã chép ✓'; btn.classList.add('copied');
        setTimeout(() => { btn.textContent = 'Sao chép'; btn.classList.remove('copied'); }, 2000);
      });
    };
    meta.appendChild(btn);
  }
  const ts = document.createElement('span'); ts.textContent = time;
  meta.appendChild(ts);
  row.appendChild(meta);
}

function addMsg(ctx, text, msgRole) {
  document.getElementById(ctx.welcomeId)?.remove();
  const row = document.createElement('div');
  row.className = 'msg-row ' + msgRole;
  const av = document.createElement('div');
  av.className = 'avatar ' + msgRole;
  av.textContent = msgRole === 'bot' ? 'AI' : (role === 'doctor' ? 'BS' : 'BN');
  const bub = document.createElement('div');
  bub.className = 'bubble';
  bub.textContent = text;
  row.appendChild(av); row.appendChild(bub);
  _addMeta(row, _fmtTime(), msgRole === 'bot' ? text : undefined);
  ctx.msgsEl.appendChild(row);
  ctx.msgsEl.scrollTop = ctx.msgsEl.scrollHeight;
  return bub;
}

function createBotBubble(ctx) {
  document.getElementById(ctx.welcomeId)?.remove();
  const row = document.createElement('div');
  row.className = 'msg-row bot';
  const av = document.createElement('div');
  av.className = 'avatar bot'; av.textContent = 'AI';
  const bub = document.createElement('div');
  bub.className = 'bubble';
  bub.innerHTML = '<div class="typing-dots"><span></span><span></span><span></span></div>';
  row.appendChild(av); row.appendChild(bub);
  ctx.msgsEl.appendChild(row);
  ctx.msgsEl.scrollTop = ctx.msgsEl.scrollHeight;
  return bub;
}

// ── Doctor image attachment state ──
let _doctorImgBase64 = '';
let _doctorImgMime   = 'image/jpeg';
let _doctorImgName   = '';

function handleDoctorFileSelect(input) {
  const file = input.files[0];
  if (!file) return;
  _doctorImgName = file.name;
  const reader = new FileReader();
  reader.onload = e => {
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement('canvas');
      canvas.width = img.width;
      canvas.height = img.height;
      canvas.getContext('2d').drawImage(img, 0, 0);
      const jpegDataUrl = canvas.toDataURL('image/jpeg', 0.92);
      _doctorImgMime = 'image/jpeg';
      _doctorImgBase64 = jpegDataUrl.split(',')[1];
      document.getElementById('d-img-thumb').src = jpegDataUrl;
      document.getElementById('d-img-name').textContent = file.name;
      document.getElementById('d-img-preview').style.display = 'flex';
    };
    img.src = e.target.result;
  };
  reader.readAsDataURL(file);
  input.value = '';
}

function clearDoctorImage() {
  _doctorImgBase64 = '';
  _doctorImgName   = '';
  document.getElementById('d-img-preview').style.display = 'none';
  document.getElementById('d-img-thumb').src = '';
}

async function sendMsg(r) {
  const ctx  = getCtx(r);
  const text = ctx.inputEl.value.trim();
  const hasImg = r === 'doctor' && _doctorImgBase64;
  if (!text && !hasImg) return;
  if (ctx.sendEl.disabled) return;

  const imgBase64 = _doctorImgBase64;
  const imgMime   = _doctorImgMime;
  const imgName   = _doctorImgName;

  ctx.inputEl.value = '';
  ctx.inputEl.style.height = 'auto';
  ctx.sendEl.disabled = true;
  if (hasImg) clearDoctorImage();

  // Show user message — with image thumbnail if attached
  if (hasImg) {
    document.getElementById(ctx.welcomeId)?.remove();
    const row = document.createElement('div');
    row.className = 'msg-row user';
    const av = document.createElement('div');
    av.className = 'avatar user'; av.textContent = 'BS';
    const bub = document.createElement('div');
    bub.className = 'bubble';
    bub.innerHTML = `<img src="data:${imgMime};base64,${imgBase64}"
      style="max-width:200px;max-height:140px;display:block;margin-bottom:${text?'6px':'0'};border:1px solid var(--ui-03);">
      ${text ? `<span>${text}</span>` : ''}`;
    row.appendChild(av); row.appendChild(bub);
    ctx.msgsEl.appendChild(row);
    ctx.msgsEl.scrollTop = ctx.msgsEl.scrollHeight;
  } else {
    addMsg(ctx, text, 'user');
  }

  const bubble = createBotBubble(ctx);

  let fullText = '', textStarted = false, badgesDiv = null;

  try {
    const res = await fetch('/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Session-Token': _sessionToken },
      body: JSON.stringify({
        message: text || 'Phân tích kết quả xét nghiệm này giúp tôi.',
        session_id: ctx.session,
        role: role,
        doctor_name:  (role === 'doctor'  && currentDoctor)  ? currentDoctor.name  : '',
        doctor_id:    (role === 'doctor'  && currentDoctor)  ? currentDoctor.id    : '',
        patient_name: (role === 'patient' && currentPatient) ? currentPatient.name : '',
        patient_id:   (role === 'patient' && currentPatient) ? currentPatient.id   : '',
        image_base64: imgBase64,
        image_mime:   imgMime,
      }),
    });

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split('\n');
      buf = lines.pop();

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        let ev;
        try { ev = JSON.parse(line.slice(6)); } catch { continue; }

        if (ev.type === 'status' && ev.text && !textStarted) {
          bubble.innerHTML = `<div class="status-line">${ev.text}</div>`;
          badgesDiv = null;

        } else if (ev.type === 'tool_call' && !textStarted) {
          if (!badgesDiv) {
            badgesDiv = document.createElement('div');
            badgesDiv.className = 'tool-badges';
            bubble.appendChild(badgesDiv);
          }
          const badge = document.createElement('span');
          badge.className = 'tool-badge';
          badge.textContent = ev.label || ev.name;
          badgesDiv.appendChild(badge);
          const st = bubble.querySelector('.status-line');
          if (st) st.textContent = ev.label || ev.name;

        } else if (ev.type === 'text') {
          if (!textStarted) { bubble.innerHTML = ''; textStarted = true; }
          fullText += ev.delta;
          bubble.innerHTML = marked.parse(fullText);
          ctx.msgsEl.scrollTop = ctx.msgsEl.scrollHeight;

        } else if (ev.type === 'done' && isDengueChecklist(fullText)) {
          bubble.innerHTML = '';
          bubble.appendChild(buildDengueForm(ctx));
          ctx.msgsEl.scrollTop = ctx.msgsEl.scrollHeight;

        } else if (ev.type === 'error') {
          bubble.textContent = 'Lỗi: ' + ev.text;

        } else if (ev.session_id) {
          ctx.setSession(ev.session_id);
        }
      }
    }
  } catch (e) {
    bubble.textContent = 'Lỗi kết nối. Vui lòng thử lại.';
  }

  // Thêm timestamp + copy vào bot bubble sau khi xong
  const botRow = bubble.closest('.msg-row');
  if (botRow && !botRow.querySelector('.msg-meta')) {
    _addMeta(botRow, _fmtTime(), fullText || bubble.textContent);
  }

  ctx.sendEl.disabled = false;
  ctx.inputEl.focus();
}

/* ── Patient slide-over panel ── */
/* ══════════════════════════════════
   CBC WIDGET
══════════════════════════════════ */
const CBC_PARAMS = [
  'Bạch cầu (WBC)','Hồng cầu (RBC)','Hemoglobin',
  'Hematocrit','Tiểu cầu (PLT)','MCV','MCH','MCHC',
  'Neutrophil %','Lymphocyte %',
];
const CBC_SHORT = {
  'Bạch cầu (WBC)':'WBC', 'Hồng cầu (RBC)':'RBC',
  'Hemoglobin':'HGB',      'Hematocrit':'HCT',
  'Tiểu cầu (PLT)':'PLT',  'MCV':'MCV',
  'MCH':'MCH',              'MCHC':'MCHC',
  'Neutrophil %':'Neu%',   'Lymphocyte %':'Lym%',
};

let _cbcChart = null;
let _cbcData  = { byDate:{}, byParam:{}, dates:[], params:[] };
let _cbcGender = 'Nam';
let _cbcViewMode = 'table';
let _cbcCurrentPatientId = '';

async function _loadCbc(patientId, gender) {
  _cbcGender           = gender;
  _cbcViewMode         = 'table';
  _cbcCurrentPatientId = patientId;
  const body = document.getElementById('cbc-body');
  if (!body) return;
  try {
    const [obsRes, dengueRes] = await Promise.all([
      fetch(`/api/observations?patient_id=${patientId}&category=laboratory&_count=100`).then(r => r.json()),
      fetch(`/api/dengue/${patientId}`).then(r => r.json()).catch(() => null),
    ]);
    _cbcProcess(obsRes.observations || []);
    _cbcRender();
    _renderDengueBanner(dengueRes);
  } catch(e) {
    if (document.getElementById('cbc-body'))
      document.getElementById('cbc-body').innerHTML =
        `<p class="pp-empty" style="padding:12px 16px">Không tải được dữ liệu CBC</p>`;
  }
}

function _renderDengueBanner(data) {
  const el = document.getElementById('dengue-banner');
  if (!el) return;
  if (!data || !data.available) { el.style.display = 'none'; return; }
  const s = data.screening || {};
  const likelihood = s.dengue_likelihood || '';
  if (!likelihood || likelihood === 'unknown') { el.style.display = 'none'; return; }

  const icons = { very_likely: '🔴', likely: '🟠', possible: '🟡', unlikely: '🟢' };
  const labels = {
    very_likely: 'Rất có thể SXHD',
    likely:      'Có thể SXHD',
    possible:    'Nghi ngờ SXHD',
    unlikely:    'Ít khả năng SXHD',
  };
  const cbc = data.cbc_used || {};
  const cbcText = [
    cbc.plt != null ? `PLT ${cbc.plt}` : '',
    cbc.wbc != null ? `WBC ${cbc.wbc}` : '',
    cbc.hct != null ? `HCT ${cbc.hct}%` : '',
  ].filter(Boolean).join(' · ');

  const findings = (s.findings || []).slice(0, 2).join('; ');
  const detail   = findings || s.interpretation || '';

  el.className  = `dengue-banner ${likelihood}`;
  el.style.display = '';
  el.innerHTML  = `
    <span class="dengue-banner-icon">${icons[likelihood] || '🦟'}</span>
    <div class="dengue-banner-body">
      <div class="dengue-banner-label">Sàng lọc SXHD · ${labels[likelihood] || likelihood}</div>
      ${detail ? `<div class="dengue-banner-detail">${detail}</div>` : ''}
      <div class="dengue-banner-date">${cbcText}${data.obs_date ? ' · ' + data.obs_date : ''}</div>
    </div>`;
}

function _cbcProcess(obs) {
  const byDate = {}, byParam = {};
  for (const o of obs) {
    if (!CBC_PARAMS.includes(o.name)) continue;
    if (!byDate[o.date]) byDate[o.date] = {};
    byDate[o.date][o.name] = { value: o.value, unit: o.unit };
    if (!byParam[o.name]) byParam[o.name] = [];
    byParam[o.name].push({ date: o.date, value: o.value });
  }
  const dates  = Object.keys(byDate).sort((a,b) => b.localeCompare(a));
  const params = CBC_PARAMS.filter(p => byParam[p]?.length);
  _cbcData = { byDate, byParam, dates, params };
}

function _cbcCls(name, value) {
  const s = valStatus(name, value, _cbcGender);
  if (!s) return 'cbc-n';
  return s.cls === 'danger' ? 'cbc-d' : s.cls === 'warning' ? 'cbc-w' : 'cbc-n';
}
function _cbcArrow(name, value) {
  const s = valStatus(name, value, _cbcGender);
  return (!s || s.cls === 'normal') ? '' : ' ' + s.arrow;
}

function _cbcToggle(view) {
  _cbcViewMode = view;
  document.getElementById('cbc-btn-tbl')?.classList.toggle('active', view === 'table');
  document.getElementById('cbc-btn-cht')?.classList.toggle('active', view === 'chart');
  _cbcRender();
}

function _cbcRender() {
  const body = document.getElementById('cbc-body');
  if (!body) return;
  if (!_cbcData.dates.length) {
    body.innerHTML = `<p class="pp-empty" style="padding:12px 16px">Không có dữ liệu CBC</p>`;
    return;
  }
  _cbcViewMode === 'table' ? _cbcRenderTable(body) : _cbcRenderChartView(body);
}

function _cbcRenderTable(body, showAll = false) {
  const { dates, params, byDate } = _cbcData;
  const LIMIT = 5;
  const visibleDates = showAll ? dates : dates.slice(0, LIMIT);
  const heads = params.map(p => `<th title="${p}">${CBC_SHORT[p]||p}</th>`).join('');
  const rows  = visibleDates.map(d => {
    const dateFmt = d.slice(5).replace('-','/') + ' <span style="color:var(--text-03)">' + d.slice(2,4) + '</span>';
    const cells = params.map(p => {
      const e = byDate[d]?.[p];
      if (!e || e.value === '') return `<td>—</td>`;
      const cls = _cbcCls(p, e.value);
      return `<td class="${cls}">${e.value}${_cbcArrow(p, e.value)}</td>`;
    }).join('');
    return `<tr><td>${dateFmt}</td>${cells}</tr>`;
  }).join('');
  const footer = (!showAll && dates.length > LIMIT)
    ? `<tr><td colspan="${params.length+1}" style="text-align:center;padding:6px">
         <a href="#" onclick="event.preventDefault();_cbcRenderTable(document.getElementById('cbc-body'),true)"
           style="font-size:11px;color:var(--brand-01)">
           Xem tất cả ${dates.length} kết quả →
         </a></td></tr>`
    : '';
  body.innerHTML = `
    <div class="cbc-tbl-wrap">
      <table class="cbc-tbl">
        <thead><tr><th>Ngày</th>${heads}</tr></thead>
        <tbody>${rows}${footer}</tbody>
      </table>
    </div>`;
}

function _cbcRenderChartView(body) {
  const { params } = _cbcData;
  const items = params.map((p,i) =>
    `<div class="cbc-param-item${i===0?' active':''}"
      onclick="_cbcParamClick(this,'${p}')">${CBC_SHORT[p]||p}</div>`
  ).join('');
  body.innerHTML = `
    <div class="cbc-chart-layout">
      <div class="cbc-param-list">${items}</div>
      <div class="cbc-chart-area">
        <canvas id="cbc-canvas" style="max-height:190px"></canvas>
      </div>
    </div>`;
  if (params[0]) _cbcDrawChart(params[0]);
}

function _cbcParamClick(el, name) {
  el.closest('.cbc-param-list').querySelectorAll('.cbc-param-item')
    .forEach(e => e.classList.remove('active'));
  el.classList.add('active');
  _cbcDrawChart(name);
}

function _cbcDrawChart(name) {
  const canvas = document.getElementById('cbc-canvas');
  if (!canvas) return;
  if (_cbcChart) { _cbcChart.destroy(); _cbcChart = null; }
  const entries = (_cbcData.byParam[name] || []).slice().sort((a,b) => a.date.localeCompare(b.date));
  const labels  = entries.map(e => e.date.slice(5).replace('-','/'));
  const values  = entries.map(e => parseFloat(e.value));
  const ref     = REFS[name] || REFS[name+'_'+_cbcGender] || {};
  _cbcChart = new Chart(canvas.getContext('2d'), {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: CBC_SHORT[name] || name,
        data: values,
        borderColor: '#005d5d',
        backgroundColor: 'rgba(0,93,93,.06)',
        tension: 0.3, fill: false,
        pointRadius: 5, pointHoverRadius: 7,
        pointBackgroundColor: values.map(v => {
          const s = valStatus(name, String(v), _cbcGender);
          if (!s) return '#005d5d';
          return s.cls==='danger'?'#da1e28':s.cls==='warning'?'#b28600':'#198038';
        }),
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { font:{size:10} } },
        y: {
          ticks: { font:{size:10} },
          suggestedMin: ref.low  ? ref.low  * 0.85 : undefined,
          suggestedMax: ref.high ? ref.high * 1.15 : undefined,
        }
      }
    }
  });
}

/* ── CBC Input Modal ── */
let _cbcModalPatientId   = '';
let _cbcModalPatientName = '';

function openCbcModal(patientId, patientName) {
  _cbcModalPatientId   = patientId;
  _cbcModalPatientName = patientName;
  document.getElementById('cbc-modal-pname').textContent = patientName;
  document.getElementById('cbc-modal-result').style.display = 'none';
  document.getElementById('cbc-modal-result').innerHTML = '';
  // Reset form
  ['plt','wbc','hct','hgb','ast','alt','fever-day'].forEach(id => {
    const el = document.getElementById('cbc-' + id);
    if (el) { el.value = ''; el.classList.remove('err'); }
  });
  // Default datetime = now (local)
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  document.getElementById('cbc-collected-at').value = now.toISOString().slice(0,16);
  document.getElementById('cbc-submit-btn').disabled = false;
  document.getElementById('cbc-submit-btn').textContent = 'Lưu kết quả CBC';
  document.getElementById('cbc-modal-overlay').classList.remove('hidden');
}

function closeCbcModal() {
  document.getElementById('cbc-modal-overlay').classList.add('hidden');
}

async function submitCbc() {
  const pltEl = document.getElementById('cbc-plt');
  pltEl.classList.remove('err');
  const plt = parseFloat(pltEl.value);
  if (isNaN(plt)) { pltEl.classList.add('err'); pltEl.focus(); return; }

  const btn = document.getElementById('cbc-submit-btn');
  btn.disabled = true;
  btn.textContent = 'Đang lưu...';

  const body = { patient_id: _cbcModalPatientId, plt };
  const fields = { wbc:'cbc-wbc', hct:'cbc-hct', hgb:'cbc-hgb',
                   ast:'cbc-ast', alt:'cbc-alt', fever_day:'cbc-fever-day' };
  for (const [key, id] of Object.entries(fields)) {
    const v = parseFloat(document.getElementById(id).value);
    if (!isNaN(v)) body[key] = v;
  }
  const ca = document.getElementById('cbc-collected-at').value;
  if (ca) body.collected_at = ca + ':00+07:00';

  try {
    const r   = await fetch('/api/cbc', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const res = await r.json();
    if (!r.ok) throw new Error(res.detail || 'Lỗi lưu CBC');

    btn.textContent = '✓ Đã lưu';
    _showCbcResult(res);
    _loadCbc(_cbcModalPatientId, _cbcGender);
  } catch(e) {
    btn.disabled = false;
    btn.textContent = 'Lưu kết quả CBC';
    const rd = document.getElementById('cbc-modal-result');
    rd.style.display = 'block';
    rd.innerHTML = `<div style="color:var(--danger);font-size:13px">⚠ ${e.message}</div>`;
  }
}

function _showCbcResult(res) {
  const rd = document.getElementById('cbc-modal-result');
  rd.style.display = 'block';
  const ds = res.dengue_screening || {};
  const risk = (ds.risk_level || '').toLowerCase();
  const riskCls = risk === 'high' ? 'cbc-result-risk-high'
                : risk === 'medium' ? 'cbc-result-risk-medium'
                : 'cbc-result-risk-low';
  const riskVI  = risk === 'high' ? 'NGUY CƠ CAO'
                : risk === 'medium' ? 'NGUY CƠ TRUNG BÌNH'
                : risk === 'low' ? 'NGUY CƠ THẤP' : '';

  const saved = Object.entries(res.cbc_saved || {})
    .map(([k,v]) => `<span style="margin-right:10px"><strong>${k}</strong> ${v}</span>`).join('');

  rd.innerHTML = `
    <div class="cbc-result">
      <div style="font-size:12px;color:var(--text-03);margin-bottom:4px">
        ✓ Đã lưu CBC — ${res.observation_date || ''}
      </div>
      <div style="margin-bottom:8px;flex-wrap:wrap;display:flex;gap:4px">${saved}</div>
      ${riskVI ? `<div style="font-size:13px">Sàng lọc SXHD:
        <span class="${riskCls}">${riskVI}</span>
        ${ds.recommendation ? `<div style="font-size:12px;color:var(--text-02);margin-top:4px">${ds.recommendation}</div>` : ''}
      </div>` : ''}
    </div>`;
}

/* ── Vitals Input Modal ── */
let _vitModalPatientId   = '';
let _vitModalPatientName = '';

function openVitalsModal(patientId, patientName) {
  _vitModalPatientId   = patientId;
  _vitModalPatientName = patientName;
  document.getElementById('vit-modal-pname').textContent = patientName;
  document.getElementById('vit-modal-result').style.display = 'none';
  document.getElementById('vit-modal-result').innerHTML = '';
  ['systolic','diastolic','heart-rate','resp-rate','temp','spo2','weight','height'].forEach(id => {
    const el = document.getElementById('vit-' + id);
    if (el) { el.value = ''; el.classList.remove('err'); }
  });
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  document.getElementById('vit-measured-at').value = now.toISOString().slice(0,16);
  document.getElementById('vit-submit-btn').disabled = false;
  document.getElementById('vit-submit-btn').textContent = 'Lưu sinh hiệu';
  document.getElementById('vit-modal-overlay').classList.remove('hidden');
}

function closeVitalsModal() {
  document.getElementById('vit-modal-overlay').classList.add('hidden');
}

async function submitVitals() {
  const fields = {
    systolic: 'vit-systolic', diastolic: 'vit-diastolic',
    heart_rate: 'vit-heart-rate', resp_rate: 'vit-resp-rate',
    temp: 'vit-temp', spo2: 'vit-spo2',
    weight: 'vit-weight', height: 'vit-height',
  };

  const body = { patient_id: _vitModalPatientId };
  let any = false;
  for (const [key, id] of Object.entries(fields)) {
    const v = parseFloat(document.getElementById(id).value);
    if (!isNaN(v)) { body[key] = v; any = true; }
  }
  if (!any) {
    const rd = document.getElementById('vit-modal-result');
    rd.style.display = 'block';
    rd.innerHTML = `<div style="color:var(--danger);font-size:13px">⚠ Nhập ít nhất 1 chỉ số sinh hiệu.</div>`;
    return;
  }
  const ma = document.getElementById('vit-measured-at').value;
  if (ma) body.measured_at = ma + ':00+07:00';

  const btn = document.getElementById('vit-submit-btn');
  btn.disabled = true;
  btn.textContent = 'Đang lưu...';

  try {
    const r   = await fetch('/api/vitals', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const res = await r.json();
    if (!r.ok) throw new Error(res.detail || 'Lỗi lưu sinh hiệu');

    btn.textContent = '✓ Đã lưu';
    _showVitalsResult(res);
  } catch(e) {
    btn.disabled = false;
    btn.textContent = 'Lưu sinh hiệu';
    const rd = document.getElementById('vit-modal-result');
    rd.style.display = 'block';
    rd.innerHTML = `<div style="color:var(--danger);font-size:13px">⚠ ${e.message}</div>`;
  }
}

function _showVitalsResult(res) {
  const rd = document.getElementById('vit-modal-result');
  rd.style.display = 'block';

  const saved = Object.entries(res.vitals_saved || {})
    .map(([k,v]) => `<span style="margin-right:10px"><strong>${k}</strong> ${v}</span>`).join('');

  const alerts = res.alerts || [];
  const hasCritical = alerts.some(a => a.severity === 'critical');
  const hasWarning  = alerts.some(a => a.severity === 'warning');

  let alertHtml = '';
  if (hasCritical) {
    const items = alerts.filter(a => a.severity === 'critical')
      .map(a => `<li><strong>${a.field}:</strong> ${a.message}</li>`).join('');
    alertHtml += `<div class="vit-alert vit-alert-critical">
      <div class="vit-alert-title">🚨 NGUY HIỂM — cần xử trí ngay</div>
      <ul>${items}</ul></div>`;
  }
  if (hasWarning) {
    const items = alerts.filter(a => a.severity === 'warning')
      .map(a => `<li><strong>${a.field}:</strong> ${a.message}</li>`).join('');
    alertHtml += `<div class="vit-alert vit-alert-warning">
      <div class="vit-alert-title">⚠ Bất thường</div>
      <ul>${items}</ul></div>`;
  }
  if (!alerts.length) {
    alertHtml = `<div class="vit-alert vit-alert-normal">
      ✓ Tất cả chỉ số trong giới hạn bình thường.</div>`;
  }

  rd.innerHTML = `
    <div class="cbc-result">
      <div style="font-size:12px;color:var(--text-03);margin-bottom:4px">
        ✓ Đã lưu sinh hiệu — ${res.observation_date || ''}
      </div>
      <div style="margin-bottom:8px;flex-wrap:wrap;display:flex;gap:4px">${saved}</div>
      ${alertHtml}
      ${res._citation ? `<div style="font-size:11px;color:var(--text-03);margin-top:8px">
        📖 ${res._citation}</div>` : ''}
    </div>`;
}

/* ── Allergy Input Modal ── */
let _allgModalPatientId = '';
let _allgModalPatientName = '';

function openAllergyModal(patientId, patientName) {
  _allgModalPatientId   = patientId;
  _allgModalPatientName = patientName;
  document.getElementById('allg-modal-pname').textContent = patientName;
  document.getElementById('allg-substance').value = '';
  document.getElementById('allg-reaction').value = '';
  document.getElementById('allg-onset').value = '';
  document.getElementById('allg-category').value = 'medication';
  document.getElementById('allg-severity').value = 'moderate';
  document.getElementById('allg-verification').value = 'unconfirmed';
  document.getElementById('allg-modal-result').style.display = 'none';
  document.getElementById('allg-modal-result').innerHTML = '';
  document.getElementById('allg-submit-btn').disabled = false;
  document.getElementById('allg-submit-btn').textContent = 'Lưu dị ứng';
  document.getElementById('allg-modal-overlay').classList.remove('hidden');
}

function closeAllergyModal() {
  document.getElementById('allg-modal-overlay').classList.add('hidden');
}

async function submitAllergy() {
  const substance = document.getElementById('allg-substance').value.trim();
  if (!substance) {
    const el = document.getElementById('allg-substance');
    el.classList.add('err'); el.focus(); return;
  }
  const body = {
    patient_id:   _allgModalPatientId,
    substance,
    category:     document.getElementById('allg-category').value,
    severity:     document.getElementById('allg-severity').value,
    reaction:     document.getElementById('allg-reaction').value.trim(),
    verification: document.getElementById('allg-verification').value,
    onset_date:   document.getElementById('allg-onset').value,
  };
  const btn = document.getElementById('allg-submit-btn');
  btn.disabled = true; btn.textContent = 'Đang lưu...';
  try {
    const r   = await fetch('/api/allergy', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const res = await r.json();
    if (!r.ok) throw new Error(res.detail || 'Lỗi lưu dị ứng');
    const rd = document.getElementById('allg-modal-result');
    rd.style.display = 'block';
    rd.innerHTML = `<div class="vit-alert vit-alert-normal">
      ✓ Đã lưu: ${substance} (${res.severity_vi})
    </div>`;
    btn.textContent = '✓ Đã lưu';
    // Reload allergies section in patient panel
    setTimeout(() => {
      closeAllergyModal();
      _loadAllergies(_allgModalPatientId);
    }, 800);
  } catch (e) {
    btn.disabled = false; btn.textContent = 'Lưu dị ứng';
    const rd = document.getElementById('allg-modal-result');
    rd.style.display = 'block';
    rd.innerHTML = `<div style="color:var(--danger);font-size:13px">⚠ ${e.message}</div>`;
  }
}

async function _loadAllergies(patientId) {
  const el = document.getElementById('allergy-body-' + patientId);
  if (!el) return;
  try {
    const r = await fetch('/api/allergies/' + patientId);
    const d = await r.json();
    el.innerHTML = _renderAllergiesHtml(d.allergies || []);
  } catch (e) {
    el.innerHTML = `<p class="pp-empty" style="color:var(--danger)">Lỗi tải dị ứng</p>`;
  }
}

function _renderAllergiesHtml(allergies) {
  if (!allergies || !allergies.length) {
    return `<p class="pp-empty">Chưa ghi nhận dị ứng nào</p>`;
  }
  return allergies.map(a => {
    const icon = a.criticality === 'high' ? '🚨' : '⚠';
    const cls  = a.criticality === 'high' ? 'allergy-high' : 'allergy-low';
    const sev  = a.severity_vi ? ` — ${a.severity_vi}` : '';
    const rxn  = a.reaction ? ` (${a.reaction})` : '';
    const cat  = a.category_vi ? `<span class="allergy-cat">${a.category_vi}</span>` : '';
    return `<div class="allergy-item ${cls}">
      ${icon} <strong>${a.substance}</strong>${sev}${rxn} ${cat}
    </div>`;
  }).join('');
}

/* ── Prescription Modal ── */
let _rxModalPatientId   = '';
let _rxModalPatientName = '';
let _rxDrugCatalog      = null;  // {category: [drug, ...]}
let _rxAllergies        = [];
let _rxMedRowSeq        = 0;
let _rxMedRows          = {};    // rowId → {drugId, checkResult, overrideReason}

async function openRxModal(patientId, patientName) {
  _rxModalPatientId   = patientId;
  _rxModalPatientName = patientName;
  _rxMedRows          = {};
  _rxMedRowSeq        = 0;
  document.getElementById('rx-modal-pname').textContent = patientName;
  document.getElementById('rx-diagnosis').value = '';
  document.getElementById('rx-medications-list').innerHTML = '';
  document.getElementById('rx-modal-result').style.display = 'none';
  document.getElementById('rx-modal-result').innerHTML = '';
  document.getElementById('rx-submit-btn').disabled = false;
  document.getElementById('rx-submit-btn').textContent = 'Lưu đơn thuốc';
  document.getElementById('rx-modal-overlay').classList.remove('hidden');

  // Load catalog + allergies in parallel
  if (!_rxDrugCatalog) {
    try {
      const r = await fetch('/api/drug-catalog');
      const d = await r.json();
      _rxDrugCatalog = d.by_category;
    } catch (e) { _rxDrugCatalog = {}; }
  }
  try {
    const r = await fetch('/api/allergies/' + patientId);
    const d = await r.json();
    _rxAllergies = d.allergies || [];
  } catch (e) { _rxAllergies = []; }

  // TIER 1: Banner dị ứng đầu form
  _renderAllergyBanner();

  // Khởi tạo 1 medication row trống
  addMedicationRow();
}

function closeRxModal() {
  document.getElementById('rx-modal-overlay').classList.add('hidden');
}

function _renderAllergyBanner() {
  const banner = document.getElementById('rx-allergy-banner');
  const medAllergies = _rxAllergies.filter(a => a.category === 'medication');
  if (!medAllergies.length) {
    banner.style.display = 'none';
    return;
  }
  const items = medAllergies.map(a => {
    const icon = a.criticality === 'high' ? '🚨' : '⚠';
    const sev = a.severity_vi || '';
    return `<li>${icon} <strong>${a.substance}</strong> ${sev ? '— ' + sev : ''} ${a.reaction ? '(' + a.reaction + ')' : ''}</li>`;
  }).join('');
  banner.style.display = 'block';
  banner.innerHTML = `
    <div class="rx-allergy-title">🚨 DỊ ỨNG THUỐC ĐÃ GHI NHẬN</div>
    <ul>${items}</ul>
  `;
}

function addMedicationRow(containerId = 'rx-medications-list') {
  const rowId = 'rx-row-' + (++_rxMedRowSeq);
  _rxMedRows[rowId] = { drugId: '', checkResult: null, overrideReason: '' };

  const drugOptions = _rxDrugCatalog
    ? Object.entries(_rxDrugCatalog).map(([cat, drugs]) =>
        `<optgroup label="${cat}">
          ${drugs.map(d => `<option value="${d.id}">${d.name} ${d.strength}</option>`).join('')}
        </optgroup>`
      ).join('')
    : '';

  const html = `
    <div class="rx-med-row" id="${rowId}">
      <div class="rx-med-head">
        <span class="rx-med-num">Thuốc #${_rxMedRowSeq}</span>
        <button type="button" class="rx-med-del" onclick="removeMedicationRow('${rowId}')" title="Xóa">✕</button>
      </div>
      <div class="rx-med-grid">
        <div class="cbc-field cbc-field-full">
          <label>Tên thuốc</label>
          <select class="rx-drug-select" onchange="onDrugSelect('${rowId}', this.value)">
            <option value="">— Chọn thuốc —</option>
            ${drugOptions}
          </select>
        </div>
        <div class="cbc-field">
          <label>Liều/lần</label>
          <input type="number" class="rx-dose" min="0.5" step="0.5" value="1">
        </div>
        <div class="cbc-field">
          <label>Số lần/ngày</label>
          <input type="number" class="rx-freq" min="1" max="6" value="2">
        </div>
        <div class="cbc-field">
          <label>Số ngày</label>
          <input type="number" class="rx-dur" min="1" max="365" value="5">
        </div>
        <div class="cbc-field cbc-field-full">
          <label>Hướng dẫn (tùy chọn)</label>
          <input type="text" class="rx-instr" placeholder="VD: Sau ăn, khi sốt > 38.5°C">
        </div>
      </div>
      <div class="rx-med-alert" id="${rowId}-alert"></div>
    </div>
  `;
  document.getElementById(containerId).insertAdjacentHTML('beforeend', html);
}

function removeMedicationRow(rowId) {
  const el = document.getElementById(rowId);
  if (el) el.remove();
  delete _rxMedRows[rowId];
}

async function onDrugSelect(rowId, drugId) {
  _rxMedRows[rowId] = _rxMedRows[rowId] || {};
  _rxMedRows[rowId].drugId = drugId;
  _rxMedRows[rowId].checkResult = null;
  _rxMedRows[rowId].overrideReason = '';

  const alertEl = document.getElementById(rowId + '-alert');
  if (!drugId) { alertEl.innerHTML = ''; return; }

  alertEl.innerHTML = `<div style="font-size:12px;color:var(--text-03);padding:6px 0">Đang kiểm tra dị ứng...</div>`;

  // TIER 2: Real-time check khi chọn thuốc
  try {
    const r = await fetch('/api/check-allergy', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ patient_id: _rxModalPatientId, drug_id: drugId }),
    });
    const d = await r.json();
    _rxMedRows[rowId].checkResult = d;
    alertEl.innerHTML = _renderCheckResult(d, rowId);
  } catch (e) {
    alertEl.innerHTML = `<div style="color:var(--danger);font-size:12px">⚠ Lỗi check dị ứng: ${e.message}</div>`;
  }
}

function _renderCheckResult(check, rowId) {
  if (!check || check.verdict === 'clear') return '';

  const checks = check.checks || [];
  const altsHtml = (check.suggested_alternatives || []).length
    ? `<div class="rx-alts">
        Đề xuất thay thế: ${check.suggested_alternatives.slice(0, 4).map(a =>
          `<button type="button" class="rx-alt-btn" onclick="setRowDrug('${rowId}','${a.id}')">${a.name}</button>`
        ).join(' ')}
      </div>`
    : '';

  if (check.verdict === 'block') {
    const items = checks.filter(c => c.severity === 'critical')
      .map(c => `<li>${c.message}</li>`).join('');
    return `
      <div class="vit-alert vit-alert-critical">
        <div class="vit-alert-title">🚨 KHÔNG ĐƯỢC KÊ — dị ứng nguy hiểm</div>
        <ul>${items}</ul>
        ${altsHtml}
        <div class="rx-override-block">
          <label style="font-size:11px;font-weight:600">Vẫn kê — Lý do (BẮT BUỘC):</label>
          <input type="text" class="rx-override-input" placeholder="VD: BN đã test pen da âm tính, theo dõi sát"
                 oninput="onOverrideChange('${rowId}', this.value)">
        </div>
      </div>`;
  }

  if (check.verdict === 'warn') {
    const items = checks.filter(c => c.severity === 'warning')
      .map(c => `<li>${c.message}</li>`).join('');
    return `
      <div class="vit-alert vit-alert-warning">
        <div class="vit-alert-title">⚠ Cảnh báo phản ứng chéo</div>
        <ul>${items}</ul>
        ${altsHtml}
      </div>`;
  }
  return '';
}

function setRowDrug(rowId, drugId) {
  const row = document.getElementById(rowId);
  if (!row) return;
  const sel = row.querySelector('.rx-drug-select');
  sel.value = drugId;
  onDrugSelect(rowId, drugId);
}

function onOverrideChange(rowId, value) {
  _rxMedRows[rowId] = _rxMedRows[rowId] || {};
  _rxMedRows[rowId].overrideReason = (value || '').trim();
}

async function submitPrescription() {
  const diagnosis = document.getElementById('rx-diagnosis').value.trim();
  if (!diagnosis) {
    const el = document.getElementById('rx-diagnosis');
    el.classList.add('err'); el.focus(); return;
  }

  // Collect medications from DOM
  const meds = [];
  let hasUnresolved = false;
  for (const [rowId, state] of Object.entries(_rxMedRows)) {
    const row = document.getElementById(rowId);
    if (!row) continue;
    const drugId = row.querySelector('.rx-drug-select').value;
    if (!drugId) continue;

    const dose = parseFloat(row.querySelector('.rx-dose').value) || 1;
    const freq = parseInt(row.querySelector('.rx-freq').value) || 1;
    const dur  = parseInt(row.querySelector('.rx-dur').value)  || null;
    const instr = row.querySelector('.rx-instr').value.trim();

    const med = {
      drug_id: drugId,
      dose_per_intake: dose,
      frequency_per_day: freq,
      duration_days: dur,
      instructions: instr,
    };

    // TIER 3: Final check — nếu critical mà chưa có override → chặn
    if (state.checkResult && state.checkResult.verdict === 'block') {
      if (!state.overrideReason || state.overrideReason.length < 5) {
        hasUnresolved = true;
        // Highlight row
        row.classList.add('rx-row-error');
        continue;
      }
      med.override_reason = state.overrideReason;
    }
    meds.push(med);
  }

  if (hasUnresolved) {
    const rd = document.getElementById('rx-modal-result');
    rd.style.display = 'block';
    rd.innerHTML = `<div class="vit-alert vit-alert-critical">
      <strong>🚨 Đơn có thuốc bị chặn do dị ứng.</strong>
      Hãy đổi thuốc khác hoặc nhập lý do override (≥5 ký tự).
    </div>`;
    return;
  }
  if (!meds.length) {
    const rd = document.getElementById('rx-modal-result');
    rd.style.display = 'block';
    rd.innerHTML = `<div style="color:var(--danger);font-size:13px">⚠ Đơn phải có ít nhất 1 thuốc.</div>`;
    return;
  }

  const btn = document.getElementById('rx-submit-btn');
  btn.disabled = true; btn.textContent = 'Đang lưu...';

  const body = {
    patient_id:      _rxModalPatientId,
    practitioner_id: (currentDoctor && currentDoctor.id) || 'unknown-doctor',
    diagnosis,
    medications:     meds,
  };

  try {
    const r = await fetch('/api/prescription', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || 'Lỗi lưu đơn thuốc');

    if (d.saved === false && d.error === 'prescription_blocked') {
      btn.disabled = false; btn.textContent = 'Lưu đơn thuốc';
      const rd = document.getElementById('rx-modal-result');
      rd.style.display = 'block';
      rd.innerHTML = `<div class="vit-alert vit-alert-critical">
        <strong>🚨 Server từ chối đơn:</strong> ${d.message}
      </div>`;
      return;
    }

    btn.textContent = '✓ Đã lưu';
    _showRxResult(d);
    setTimeout(() => {
      closeRxModal();
      _loadPrescriptions(_rxModalPatientId);
    }, 1500);
  } catch (e) {
    btn.disabled = false; btn.textContent = 'Lưu đơn thuốc';
    const rd = document.getElementById('rx-modal-result');
    rd.style.display = 'block';
    rd.innerHTML = `<div style="color:var(--danger);font-size:13px">⚠ ${e.message}</div>`;
  }
}

function _showRxResult(d) {
  const rd = document.getElementById('rx-modal-result');
  rd.style.display = 'block';
  const meds = (d.medications || []).map(m =>
    `<li><strong>${m.drug_name}</strong> — ${m.instruction} ${m.override ? '⚠override' : ''}</li>`
  ).join('');
  const warnHtml = (d.warnings || []).length
    ? `<div class="vit-alert vit-alert-warning" style="margin-top:8px">
        ${d.warnings.map(w => `<div>⚠ ${w.drug_name}: ${(w.checks[0]||{}).message || ''}</div>`).join('')}
       </div>`
    : '';
  rd.innerHTML = `
    <div class="cbc-result">
      <div style="font-size:12px;color:var(--text-03);margin-bottom:4px">
        ✓ Đã kê đơn — ${d.prescription_date} — ${d.diagnosis}
      </div>
      <ul style="margin:6px 0 0 18px;font-size:13px">${meds}</ul>
      ${warnHtml}
    </div>`;
}

async function _loadPrescriptions(patientId) {
  const el = document.getElementById('rx-body-' + patientId);
  if (!el) return;
  try {
    const r = await fetch('/api/prescriptions/' + patientId);
    const d = await r.json();
    el.innerHTML = _renderPrescriptionsHtml(d.prescriptions || []);
  } catch (e) {
    el.innerHTML = `<p class="pp-empty" style="color:var(--danger)">Lỗi tải đơn thuốc</p>`;
  }
}

function _renderPrescriptionsHtml(prescriptions) {
  if (!prescriptions || !prescriptions.length) {
    return `<p class="pp-empty">Chưa có đơn thuốc nào</p>`;
  }
  return prescriptions.map(rx => {
    const meds = (rx.medications || []).map(m =>
      `<li><strong>${m.drug_name}</strong> — ${m.instruction || ''} ${m.override_note ? '<span class="rx-override-badge">override</span>' : ''}</li>`
    ).join('');
    return `<div class="rx-history-item">
      <div class="rx-history-head">
        <span class="rx-history-date">${rx.prescription_date || '—'}</span>
        ${rx.diagnosis ? `<span class="rx-history-dx">— ${rx.diagnosis}</span>` : ''}
        ${rx.has_override ? '<span class="rx-override-badge">⚠ override</span>' : ''}
      </div>
      <ul style="margin:4px 0 0 18px;font-size:12px">${meds}</ul>
    </div>`;
  }).join('');
}

function openMyProfile() {
  if (!currentPatient) { showToast('Vui lòng đăng nhập để xem hồ sơ'); return; }
  openPatientPanel(currentPatient.id);
}

function openPatientPanel(patientId, initialTab = 'overview') {
  const panel    = document.getElementById('patient-panel');
  const backdrop = document.getElementById('panel-backdrop');
  const content  = document.getElementById('panel-content');
  panel._initialTab = initialTab;

  // Skeleton loading
  content.innerHTML = `
    <div class="pp-header">
      <div class="pp-header-row">
        <div>
          <div style="background:rgba(255,255,255,.25);height:16px;width:140px;border-radius:2px;margin-bottom:8px;animation:pulse 1.2s infinite"></div>
          <div style="background:rgba(255,255,255,.15);height:12px;width:100px;border-radius:2px;animation:pulse 1.2s infinite"></div>
        </div>
        <button class="pp-close" onclick="closePatientPanel()">✕</button>
      </div>
    </div>
    <div class="pp-section">
      ${[1,2,3].map(() => `<div class="pp-row"><span style="background:var(--ui-03);height:12px;width:80px;display:inline-block;border-radius:2px;animation:pulse 1.2s infinite"></span><span style="background:var(--ui-03);height:12px;width:60px;display:inline-block;border-radius:2px;animation:pulse 1.2s infinite"></span></div>`).join('')}
    </div>`;

  panel.classList.add('open');
  backdrop.classList.add('open');

  fetch(`/api/patient/${patientId}`)
    .then(r => r.json())
    .then(d => renderPatientPanel(d, panel._initialTab || 'overview'))
    .catch(e => {
      content.innerHTML = `<div class="pp-section"><p style="color:var(--danger)">Lỗi tải dữ liệu: ${e.message}</p></div>`;
    });
}

// ── Ngưỡng tham chiếu (tên theo _LOINC_VI) ──
const REFS = {
  // Sinh hiệu
  'HA tâm thu':       { low:90,  high:120, warnHigh:139, dangerHigh:180 },
  'HA tâm trương':    { low:60,  high:80,  warnHigh:89,  dangerHigh:120 },
  'Nhịp tim':         { low:60,  high:100, dangerLow:40,  dangerHigh:150 },
  'Nhịp thở':         { low:12,  high:20,  warnHigh:24 },
  'Nhiệt độ':         { low:36.1,high:37.2,warnHigh:38,  dangerHigh:39 },
  'SpO2':             { low:95,  high:100, warnLow:91,   dangerLow:90 },
  'BMI':              { low:18.5,high:22.9,warnHigh:27.5 },
  // Sinh hóa
  'Glucose máu':      { low:3.9, high:6.1, warnHigh:6.9, dangerLow:3.0, dangerHigh:11 },
  'HbA1c':            { low:0,   high:5.6, warnHigh:6.4 },
  'Cholesterol TP':   { low:0,   high:5.2, warnHigh:6.2 },
  'Ure':              { low:2.5, high:7.5 },
  'Creatinine_Nam':   { low:62,  high:115 },
  'Creatinine_Nữ':    { low:44,  high:97  },
  // CBC — phân biệt giới tính cho RBC, HGB, HCT
  'Bạch cầu (WBC)':   { low:4.5, high:11.0, dangerLow:2.0, dangerHigh:30 },
  'Hồng cầu (RBC)_Nam':{ low:4.5,high:5.9,  dangerLow:3.0 },
  'Hồng cầu (RBC)_Nữ': { low:4.0,high:5.2,  dangerLow:2.5 },
  'Hemoglobin_Nam':   { low:13.5,high:17.5, dangerLow:7.0,  dangerHigh:20 },
  'Hemoglobin_Nữ':    { low:12.0,high:15.5, dangerLow:7.0,  dangerHigh:20 },
  'Hematocrit_Nam':   { low:41,  high:53 },
  'Hematocrit_Nữ':    { low:36,  high:46 },
  'Tiểu cầu (PLT)':   { low:150, high:400, dangerLow:50,   dangerHigh:1000 },
  'MCV':              { low:80,  high:100 },
  'MCH':              { low:27,  high:33 },
  'MCHC':             { low:32,  high:36 },
  'Neutrophil %':     { low:50,  high:70 },
  'Lymphocyte %':     { low:20,  high:40 },
};

const GENDER_SPLIT = ['Creatinine','Hồng cầu (RBC)','Hemoglobin','Hematocrit'];
function valStatus(name, value, gender) {
  const base = GENDER_SPLIT.find(n => name.startsWith(n));
  const key  = base ? `${base}_${gender}` : name;
  const ref = REFS[key];
  if (!ref) return null;
  const v = parseFloat(value);
  if (isNaN(v)) return null;
  if (ref.dangerLow  !== undefined && v <= ref.dangerLow)  return { cls:'danger',  arrow:'↓↓' };
  if (ref.dangerHigh !== undefined && v >= ref.dangerHigh) return { cls:'danger',  arrow:'↑↑' };
  if (ref.warnLow    !== undefined && v <  ref.warnLow)    return { cls:'warning', arrow:'↓' };
  if (ref.warnHigh   !== undefined && v >  ref.warnHigh)   return { cls:'warning', arrow:'↑' };
  if (ref.low        !== undefined && v <  ref.low)        return { cls:'warning', arrow:'↓' };
  if (ref.high       !== undefined && v >  ref.high)       return { cls:'warning', arrow:'↑' };
  return { cls:'normal', arrow:'✓' };
}

function renderPatientPanel(d, initialTab = 'overview') {
  const STATUS_VI = { booked: 'Đã xác nhận', fulfilled: 'Đã khám', cancelled: 'Đã hủy', noshow: 'Vắng mặt', pending: 'Chờ xác nhận' };
  const STATUS_CL = { booked: '#198038', fulfilled: '#525252', cancelled: '#da1e28', noshow: '#b28600' };

  const initials = d.name
    ? d.name.trim().split(/\s+/).slice(-2).map(w => w[0]).join('').toUpperCase()
    : '?';
  const metaParts = [d.gender, d.age ? d.age + ' tuổi' : '', d.birth_date ? d.birth_date.split('-').reverse().join('/') : '', d.phone].filter(Boolean);

  function obsRow(v) {
    const s = valStatus(v.name, v.value, d.gender);
    const badge = s ? `<span class="val-badge val-${s.cls}">${s.arrow}</span>` : '';
    const valCls = s ? `val-text-${s.cls}` : '';
    return `
      <div class="pp-row">
        <span class="pp-row-label">${v.name}</span>
        <span style="display:flex;align-items:center;gap:5px">
          ${badge}
          <span class="pp-row-val ${valCls}">${v.value} ${v.unit}</span>
          <span class="pp-row-date">${v.date?.slice(5).replace('-','/')}</span>
        </span>
      </div>`;
  }

  const vitalsHTML = d.vitals?.length
    ? d.vitals.map(obsRow).join('')
    : `<p class="pp-empty">Chưa có dữ liệu sinh hiệu</p>`;

  const labsHTML = d.labs?.length
    ? d.labs.map(obsRow).join('')
    : `<p class="pp-empty">Chưa có kết quả xét nghiệm</p>`;

  const apptsHTML = d.appointments?.length
    ? d.appointments.map(a => `
        <div class="pp-appt-row">
          <div class="pp-appt-time">${a.start.slice(0,10).split('-').reverse().join('/')} ${a.start.slice(11,16)}</div>
          <div class="pp-appt-dept">${a.department} · <span style="color:${STATUS_CL[a.status]||'#525252'}">${STATUS_VI[a.status]||a.status}</span></div>
        </div>`).join('')
    : `<p class="pp-empty">Không có lịch hẹn sắp tới</p>`;

  document.getElementById('panel-content').innerHTML = `
    <div class="pp-header">
      <div class="pp-header-row">
        <div style="display:flex;align-items:center;gap:10px">
          <div style="width:36px;height:36px;border-radius:50%;
            background:rgba(255,255,255,.2);border:2px solid rgba(255,255,255,.4);
            display:flex;align-items:center;justify-content:center;
            font-size:13px;font-weight:700;flex-shrink:0">${initials}</div>
          <div>
            <div class="pp-name">${d.name}</div>
            <div class="pp-meta">${metaParts.join(' · ')}</div>
          </div>
        </div>
        <button class="pp-close" onclick="closePatientPanel()">✕</button>
      </div>
      ${role === 'doctor' ? `<div style="padding:8px 0 4px">
        <button onclick="closePatientPanel();fillD('Tóm tắt hồ sơ bệnh nhân ${d.name.replace(/'/g,"&#39;")}')"
          style="width:100%;background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.25);
            color:#fff;font-family:inherit;font-size:12px;font-weight:500;
            padding:6px 12px;cursor:pointer;text-align:left;transition:background .1s"
          onmouseover="this.style.background='rgba(255,255,255,.22)'"
          onmouseout="this.style.background='rgba(255,255,255,.12)'">
          🤖 Hỏi AI về bệnh nhân này
        </button>
      </div>` : ''}
    </div>
    <div class="pp-section">
      <div class="cbc-header">
        <span class="pp-section-title" style="margin:0;flex:1">Sinh hiệu</span>
        ${role === 'doctor' ? `<button onclick="openVitalsModal('${d.id}','${d.name.replace(/'/g,"&#39;")}')"
          style="background:var(--brand-01);border:none;color:#fff;
            font-family:inherit;font-size:11px;font-weight:600;
            padding:4px 8px;cursor:pointer;white-space:nowrap">
          ＋ Nhập sinh hiệu
        </button>` : ''}
      </div>
      ${vitalsHTML}
    </div>
    <div class="pp-section">
      <div class="cbc-header">
        <span class="pp-section-title" style="margin:0;flex:1">Dị ứng</span>
        ${role === 'doctor' ? `<button onclick="openAllergyModal('${d.id}','${d.name.replace(/'/g,"&#39;")}')"
          style="background:var(--brand-01);border:none;color:#fff;
            font-family:inherit;font-size:11px;font-weight:600;
            padding:4px 8px;cursor:pointer;white-space:nowrap">
          ＋ Thêm dị ứng
        </button>` : ''}
      </div>
      <div id="allergy-body-${d.id}" style="padding:8px 16px">
        <p class="pp-empty">Đang tải...</p>
      </div>
    </div>
    <div class="pp-section">
      <div class="cbc-header">
        <span class="pp-section-title" style="margin:0;flex:1">Đơn thuốc</span>
        ${role === 'doctor' ? `<button onclick="openRxModal('${d.id}','${d.name.replace(/'/g,"&#39;")}')"
          style="background:var(--brand-01);border:none;color:#fff;
            font-family:inherit;font-size:11px;font-weight:600;
            padding:4px 8px;cursor:pointer;white-space:nowrap">
          ＋ Kê đơn mới
        </button>` : ''}
      </div>
      <div id="rx-body-${d.id}" style="padding:8px 16px">
        <p class="pp-empty">Đang tải...</p>
      </div>
    </div>
    <div class="pp-section" style="padding:0">
      <div class="cbc-header">
        <span class="pp-section-title" style="margin:0;flex:1">XÉT NGHIỆM — CBC</span>
        <button class="cbc-view-btn active" id="cbc-btn-tbl" onclick="_cbcToggle('table')" title="Bảng">☰</button>
        <button class="cbc-view-btn" id="cbc-btn-cht" onclick="_cbcToggle('chart')" title="Biểu đồ">〜</button>
        ${role === 'doctor' ? `<button onclick="openCbcModal('${d.id}','${d.name.replace(/'/g,"&#39;")}')"
          style="margin-left:6px;background:var(--brand-01);border:none;color:#fff;
            font-family:inherit;font-size:11px;font-weight:600;
            padding:4px 8px;cursor:pointer;white-space:nowrap">
          ＋ Nhập CBC
        </button>` : ''}
      </div>
      <div id="dengue-banner" style="display:none"></div>
      <div id="cbc-body" style="padding:8px 16px">
        <p class="pp-empty">Đang tải...</p>
      </div>
    </div>
    <div class="pp-section">
      <div class="pp-section-title">Lịch hẹn sắp tới</div>
      ${apptsHTML}
    </div>`;

  // Inject tab bar right after header
  const headerEl = document.querySelector('#panel-content .pp-header');
  if (headerEl) {
    const tabBar = document.createElement('div');
    tabBar.className = 'pp-tab-bar';
    const notesLabel = role === 'patient' ? '📋 Ghi chú bác sĩ' : '📋 Ghi chú lâm sàng';
    tabBar.innerHTML = `
      <button class="pp-tab" id="pp-tab-overview" onclick="switchPanelTab('overview','${d.id}','${d.gender}')">Tổng quan</button>
      <button class="pp-tab" id="pp-tab-notes"    onclick="switchPanelTab('notes','${d.id}','${d.gender}')">${notesLabel}</button>`;
    headerEl.after(tabBar);
  }

  // Notes panel (hidden by default)
  const notesPanel = document.createElement('div');
  notesPanel.id = 'pp-notes-panel';
  notesPanel.style.display = 'none';
  document.getElementById('panel-content').appendChild(notesPanel);

  _loadCbc(d.id, d.gender);
  _loadAllergies(d.id);
  _loadPrescriptions(d.id);
  switchPanelTab(initialTab, d.id, d.gender);
}

function switchPanelTab(tab, patientId, gender) {
  const isNotes = tab === 'notes';
  document.getElementById('pp-tab-overview')?.classList.toggle('active', !isNotes);
  document.getElementById('pp-tab-notes')?.classList.toggle('active', isNotes);

  // Toggle visibility of all pp-section divs (overview content)
  document.querySelectorAll('#panel-content .pp-section').forEach(el => {
    el.style.display = isNotes ? 'none' : '';
  });
  const notesPanel = document.getElementById('pp-notes-panel');
  if (notesPanel) notesPanel.style.display = isNotes ? 'block' : 'none';

  if (isNotes && patientId) _loadPanelNotes(patientId);
}

async function _loadPanelNotes(patientId) {
  const el = document.getElementById('pp-notes-panel');
  if (!el) return;
  el.innerHTML = '<div style="padding:16px;color:var(--text-03);font-size:13px">Đang tải...</div>';
  try {
    // Fetch ClinicalImpression + Prescriptions song song
    const [ciResp, rxResp] = await Promise.all([
      fetch(`/api/patient/${patientId}/clinical-impressions`).then(r => r.json()),
      fetch(`/api/prescriptions/${patientId}`).then(r => r.json()),
    ]);
    const impressions   = ciResp.impressions   || [];
    const prescriptions = rxResp.prescriptions || [];

    if (!impressions.length && !prescriptions.length) {
      el.innerHTML = '<div style="padding:24px 16px;text-align:center;color:var(--text-03);font-size:13px">Chưa có ghi chú lâm sàng nào</div>';
      return;
    }

    // Match prescriptions với impression: cùng ngày HOẶC cùng chẩn đoán
    function findMatchingRxs(ci) {
      return prescriptions.filter(rx => {
        const sameDate = ci.date && rx.prescription_date && rx.prescription_date === ci.date;
        const sameDx   = ci.diagnosis && rx.diagnosis &&
          ci.diagnosis.trim().toLowerCase() === rx.diagnosis.trim().toLowerCase();
        return sameDate || sameDx;
      });
    }

    // Build cards cho mỗi lần khám (từ ClinicalImpression)
    const matchedRxIds = new Set();
    const ciCards = impressions.map(ci => {
      const matchingRxs = findMatchingRxs(ci);
      matchingRxs.forEach(rx => matchedRxIds.add(rx.prescription_id));
      const medsHtml = matchingRxs.length
        ? `<div class="pp-note-row pp-note-rx-block">
            <span class="pp-note-label">Đơn thuốc</span>
            <div class="pp-note-val">
              ${matchingRxs.map(rx =>
                `<ul style="margin:0 0 6px 18px;padding:0">${
                  (rx.medications || []).map(m =>
                    `<li><strong>${m.drug_name}</strong> — ${m.instruction || ''} ${m.override_note ? '<span class="rx-override-badge">override</span>' : ''}</li>`
                  ).join('')
                }</ul>`
              ).join('')}
            </div>
          </div>`
        : '';
      return `
        <div class="pp-note-card">
          <div class="pp-note-date">📅 ${ci.date ? ci.date.split('-').reverse().join('/') : '—'}</div>
          ${ci.diagnosis ? `<div class="pp-note-row"><span class="pp-note-label">Chẩn đoán</span><span class="pp-note-val">${ci.diagnosis}</span></div>` : ''}
          ${ci.notes     ? `<div class="pp-note-row"><span class="pp-note-label">Ghi chú</span><span class="pp-note-val">${ci.notes}</span></div>` : ''}
          ${ci.plan      ? `<div class="pp-note-row"><span class="pp-note-label">Kế hoạch</span><span class="pp-note-val">${ci.plan}</span></div>` : ''}
          ${medsHtml}
        </div>`;
    });

    // Đơn thuốc còn lại (không match với ClinicalImpression nào) → hiển thị card riêng
    const orphanRxCards = prescriptions
      .filter(rx => !matchedRxIds.has(rx.prescription_id))
      .map(rx => `
        <div class="pp-note-card pp-note-card-rx-only">
          <div class="pp-note-date">📅 ${rx.prescription_date ? rx.prescription_date.split('-').reverse().join('/') : '—'} — Kê đơn</div>
          ${rx.diagnosis ? `<div class="pp-note-row"><span class="pp-note-label">Chẩn đoán</span><span class="pp-note-val">${rx.diagnosis}</span></div>` : ''}
          <div class="pp-note-row pp-note-rx-block">
            <span class="pp-note-label">Đơn thuốc</span>
            <div class="pp-note-val">
              <ul style="margin:0 0 0 18px;padding:0">${
                (rx.medications || []).map(m =>
                  `<li><strong>${m.drug_name}</strong> — ${m.instruction || ''} ${m.override_note ? '<span class="rx-override-badge">override</span>' : ''}</li>`
                ).join('')
              }</ul>
            </div>
          </div>
        </div>`);

    el.innerHTML = ciCards.concat(orphanRxCards).join('');
  } catch (e) {
    el.innerHTML = `<div style="padding:16px;color:var(--danger);font-size:13px">Lỗi: ${e.message}</div>`;
  }
}

function closePatientPanel() {
  document.getElementById('patient-panel').classList.remove('open');
  document.getElementById('panel-backdrop').classList.remove('open');
}

/* ── Dengue screening form ── */
function isDengueChecklist(text) {
  return text.includes('A. Dịch tễ') &&
         text.includes('B. Triệu chứng') &&
         text.includes('C. Dấu hiệu cảnh báo');
}

function buildDengueForm(ctx) {
  const uid = 'df-' + Date.now();
  const yesNo = (name, val) => `
    <div class="dengue-toggle">
      <input type="radio" name="${uid}-${name}" id="${uid}-${name}-y" value="có">
      <label for="${uid}-${name}-y">Có</label>
      <input type="radio" name="${uid}-${name}" id="${uid}-${name}-n" value="không" checked>
      <label for="${uid}-${name}-n">Không</label>
    </div>`;

  const form = document.createElement('div');
  form.className = 'dengue-form';
  form.innerHTML = `
    <div class="dengue-form-title">🦟 Phiếu sàng lọc Sốt xuất huyết</div>

    <div class="dengue-section">
      <div class="dengue-section-label">A. Dịch tễ</div>
      <div class="dengue-q">
        <div class="dengue-q-label">Bạn đang sống/vừa đến vùng có dịch?</div>
        ${yesNo('epi', '')}
      </div>
      <div class="dengue-q">
        <div class="dengue-q-label">Sốt mấy ngày rồi? <span>(0 = không sốt)</span></div>
        <input type="number" class="dengue-number" id="${uid}-fever" min="0" max="30" value="0">
      </div>
    </div>

    <div class="dengue-section">
      <div class="dengue-section-label">B. Triệu chứng</div>
      <div class="dengue-q">
        <div class="dengue-q-label">Buồn nôn hoặc nôn ói</div>
        ${yesNo('s3', '')}
      </div>
      <div class="dengue-q">
        <div class="dengue-q-label">Phát ban, nổi mẩn đỏ trên da</div>
        ${yesNo('s4', '')}
      </div>
      <div class="dengue-q">
        <div class="dengue-q-label">Đau cơ, đau khớp, nhức hai hố mắt</div>
        ${yesNo('s5', '')}
      </div>
      <div class="dengue-q">
        <div class="dengue-q-label">Chấm đỏ dưới da hoặc bầm tím không rõ nguyên nhân</div>
        ${yesNo('s6', '')}
      </div>
    </div>

    <div class="dengue-section">
      <div class="dengue-section-label">C. Dấu hiệu cảnh báo</div>
      <div class="dengue-q">
        <div class="dengue-q-label">Đau bụng nhiều hoặc đau vùng gan</div>
        ${yesNo('w7', '')}
      </div>
      <div class="dengue-q">
        <div class="dengue-q-label">Nôn ói liên tục nhiều lần</div>
        ${yesNo('w8', '')}
      </div>
      <div class="dengue-q">
        <div class="dengue-q-label">Chảy máu chân răng, mũi, phân đen</div>
        ${yesNo('w9', '')}
      </div>
      <div class="dengue-q">
        <div class="dengue-q-label">Đi tiểu ít hoặc nước tiểu sẫm màu</div>
        ${yesNo('w10', '')}
      </div>
      <div class="dengue-q">
        <div class="dengue-q-label">Vật vã, lờ đờ, mệt lả nhiều</div>
        ${yesNo('w11', '')}
      </div>
    </div>

    <button class="dengue-submit" onclick="submitDengueForm('${uid}', this)">
      Gửi kết quả sàng lọc →
    </button>`;
  return form;
}

function submitDengueForm(uid, btn) {
  const r = name => {
    const el = document.querySelector(`input[name="${uid}-${name}"]:checked`);
    return el ? el.value : 'không';
  };
  const fever = document.getElementById(`${uid}-fever`)?.value || '0';

  const ans = [
    `1. Vùng dịch: ${r('epi')}`,
    `2. Số ngày sốt: ${fever}`,
    `3. Buồn nôn/nôn ói: ${r('s3')}`,
    `4. Phát ban/nổi mẩn: ${r('s4')}`,
    `5. Đau cơ, khớp, nhức hố mắt: ${r('s5')}`,
    `6. Chấm đỏ dưới da/bầm tím: ${r('s6')}`,
    `7. Đau bụng nhiều/đau vùng gan: ${r('w7')}`,
    `8. Nôn ói liên tục: ${r('w8')}`,
    `9. Chảy máu chân răng, mũi, phân đen: ${r('w9')}`,
    `10. Tiểu ít/nước tiểu sẫm: ${r('w10')}`,
    `11. Vật vã, lờ đờ, mệt lả: ${r('w11')}`,
  ].join('\n');

  btn.disabled = true;
  btn.textContent = 'Đang gửi...';

  // Xác định role hiện tại
  const ctx = getCtx(role);
  ctx.inputEl.value = ans;
  sendMsg(role);
}

/* ══════════════════════════════════════════
   BOOKING FLOW
══════════════════════════════════════════ */
const _DEPT_ICONS = {
  CARDIO:'❤️', NEURO:'🧠', GASTRO:'🫁', ENDO:'💉', ENT:'👂',
  ORTHO:'🦴', OB:'🤰', DERM:'🩹', OPHTHAL:'👁️', OPHTHO:'👁️', PEDIA:'👶', PEDS:'👶',
  URO:'🏥', UROLOGY:'🔬', ONCO:'🔬', NEPHRO:'🩺', PULM:'🫀',
  RHEUM:'🦾', PSYCH:'🧘', EMERG:'🚨', SURG:'🔪', ICU:'🛌', GEN:'🏥',
  DEFAULT:'🏥',
};
const _DEPT_NAMES = {
  CARDIO:'Tim mạch', NEURO:'Thần kinh', ORTHO:'Chỉnh hình', PEDS:'Nhi', PEDIA:'Nhi',
  OB:'Sản phụ khoa', DERM:'Da liễu', ENT:'Tai mũi họng', OPHTHO:'Mắt', OPHTHAL:'Mắt',
  GASTRO:'Tiêu hóa', ENDO:'Nội tiết', NEPHRO:'Thận', PULM:'Hô hấp',
  RHEUM:'Cơ xương khớp', ONCO:'Ung bướu', URO:'Tiết niệu', UROLOGY:'Tiết niệu',
  PSYCH:'Tâm thần', EMERG:'Cấp cứu', SURG:'Ngoại', ICU:'Hồi sức', GEN:'Đa khoa'
};

let _bkStep = 0;
let _bkData = {};

function openBooking() {
  _bkStep = 1; _bkData = {};
  document.getElementById('booking-overlay').classList.remove('hidden');
  _bkRenderStep();
}
function closeBooking() {
  document.getElementById('booking-overlay').classList.add('hidden');
}

function _bkUpdateSteps() {
  const labels = ['Chọn khoa','Bác sĩ','Ngày & Giờ','Thông tin'];
  document.getElementById('bk-steps').innerHTML = labels.map((l, i) => {
    const n = i + 1;
    const cls = n < _bkStep ? 'done' : n === _bkStep ? 'active' : '';
    return `<div class="bk-step ${cls}">${n < _bkStep ? '✓ ' : ''}${l}</div>`;
  }).join('');
}

function _bkRenderStep() {
  _bkUpdateSteps();
  if (_bkStep === 1) _bkStep1();
  else if (_bkStep === 2) _bkStep2();
  else if (_bkStep === 3) _bkStep3();
  else if (_bkStep === 4) _bkStep4();
}

async function _bkStep1() {
  const body = document.getElementById('bk-body');
  body.innerHTML = '<div class="bk-loading">Đang tải danh sách khoa...</div>';
  try {
    const data = await fetch('/api/departments').then(r => r.json());
    const depts = data.departments || [];
    body.innerHTML = `
      <div class="bk-title">Chọn khoa khám</div>
      <div class="bk-dept-grid">
        ${depts.map(d => `
          <div class="bk-dept-card" onclick="_bkSelectDept('${d.code}','${d.name.replace(/'/g,"\\'")}')">
            <div class="bk-dept-icon">${_DEPT_ICONS[d.code] || _DEPT_ICONS.DEFAULT}</div>
            <div class="bk-dept-name">${d.name}</div>
          </div>`).join('')}
      </div>`;
  } catch(e) {
    body.innerHTML = `<p style="color:var(--danger)">Lỗi tải khoa: ${e.message}</p>`;
  }
}

function _bkSelectDept(code, name) {
  _bkData.dept_code = code; _bkData.dept_name = name;
  _bkStep = 2; _bkRenderStep();
}

async function _bkStep2() {
  const body = document.getElementById('bk-body');
  body.innerHTML = '<div class="bk-loading">Đang tải danh sách bác sĩ...</div>';
  try {
    const data = await fetch(`/api/schedules?department=${_bkData.dept_code}`).then(r => r.json());
    const schedules = data.schedules || [];
    body.innerHTML = `
      <div class="bk-back" onclick="_bkStep=1;_bkRenderStep()">← Quay lại</div>
      <div class="bk-title">Chọn bác sĩ — ${_bkData.dept_name}</div>
      <div class="bk-doc-list">
        ${schedules.map(s => `
          <div class="bk-doc-item" onclick="_bkSelectDoc('${s.schedule_id}','${s.doctor_name.replace(/'/g,"\\'")}','${s.practitioner_id}')">
            <div class="bk-doc-avatar" style="background:${_avatarColor(s.doctor_name)}">${_practInitials(s.doctor_name)}</div>
            <div>
              <div class="bk-doc-name">${s.doctor_name}</div>
              <div class="bk-doc-spec">${s.department}</div>
            </div>
            <span style="margin-left:auto;color:var(--text-03);font-size:18px">›</span>
          </div>`).join('')}
      </div>`;
  } catch(e) {
    body.innerHTML = `<p style="color:var(--danger)">Lỗi: ${e.message}</p>`;
  }
}

function _bkSelectDoc(schedId, name, practId) {
  _bkData.schedule_id = schedId;
  _bkData.doctor_name = name;
  _bkData.practitioner_id = practId;
  _bkStep = 3; _bkRenderStep();
}

function _bkStep3() {
  const today = new Date().toISOString().split('T')[0];
  const body = document.getElementById('bk-body');
  body.innerHTML = `
    <div class="bk-back" onclick="_bkStep=2;_bkRenderStep()">← Quay lại</div>
    <div class="bk-title">Chọn ngày & giờ</div>
    <div class="bk-label">Ngày khám</div>
    <input type="date" class="bk-date-input" id="bk-date" value="${today}" min="${today}"
           onchange="_bkLoadSlots(this.value)">
    <div id="bk-slots-area"></div>`;
  _bkLoadSlots(today);
}

async function _bkLoadSlots(date) {
  const area = document.getElementById('bk-slots-area');
  area.innerHTML = '<div class="bk-loading" style="padding:20px 0">Đang tải slot...</div>';
  try {
    const data = await fetch(`/api/slots?schedule_id=${_bkData.schedule_id}&date=${date}`).then(r => r.json());
    const slots = data.slots || [];
    if (!slots.length) {
      area.innerHTML = '<p style="color:var(--text-02);font-size:13px;text-align:center;padding:16px 0">Không có slot trống ngày này — thử ngày khác.</p>';
      return;
    }
    area.innerHTML = `
      <div class="bk-label">Giờ khám còn trống</div>
      <div class="bk-slots">
        ${slots.map(s => `
          <button class="bk-slot" id="slot-${s.slot_id}"
            onclick="_bkSelectSlot('${s.slot_id}','${date}','${s.start_time}','${s.end_time}',this)">
            ${s.start_time}
          </button>`).join('')}
      </div>`;
  } catch(e) {
    area.innerHTML = `<p style="color:var(--danger);font-size:13px">Lỗi: ${e.message}</p>`;
  }
}

function _bkSelectSlot(slotId, date, startTime, endTime, btn) {
  document.querySelectorAll('.bk-slot').forEach(b => b.classList.remove('sel'));
  btn.classList.add('sel');
  _bkData.slot_id = slotId; _bkData.date = date;
  _bkData.start_time = startTime; _bkData.end_time = endTime;
  setTimeout(() => { _bkStep = 4; _bkRenderStep(); }, 250);
}

function _bkStep4() {
  const body = document.getElementById('bk-body');
  body.innerHTML = `
    <div class="bk-back" onclick="_bkStep=3;_bkRenderStep()">← Quay lại</div>
    <div class="bk-title">Thông tin đặt lịch</div>
    <div class="bk-summary">
      <strong>${_bkData.dept_name}</strong><br>
      ${_bkData.doctor_name}<br>
      📅 ${_bkData.date} &nbsp;⏰ ${_bkData.start_time} – ${_bkData.end_time}
    </div>
    <div class="bk-form">
      <div class="bk-field">
        <div class="bk-label">Họ và tên bệnh nhân *</div>
        <input class="bk-input" id="bk-name" type="text" placeholder="Nguyễn Văn A">
      </div>
      <div class="bk-field">
        <div class="bk-label">Số điện thoại</div>
        <input class="bk-input" id="bk-phone" type="tel" placeholder="09xx xxx xxx">
      </div>
      <div class="bk-field">
        <div class="bk-label">Lý do khám</div>
        <input class="bk-input" id="bk-reason" type="text" placeholder="Đau ngực, khó thở...">
      </div>
    </div>
    <button class="bk-submit" onclick="_bkSubmit()">Xác nhận đặt lịch →</button>`;
  document.getElementById('bk-name').focus();
}

async function _bkSubmit() {
  const name   = document.getElementById('bk-name').value.trim();
  const phone  = document.getElementById('bk-phone').value.trim();
  const reason = document.getElementById('bk-reason').value.trim();
  if (!name) {
    document.getElementById('bk-name').classList.add('err');
    document.getElementById('bk-name').focus(); return;
  }
  _bkData.patient_name = name;

  const body = document.getElementById('bk-body');
  body.innerHTML = '<div class="bk-loading">Đang đặt lịch...</div>';

  try {
    const res = await fetch('/api/book-appointment', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        slot_id: _bkData.slot_id, schedule_id: _bkData.schedule_id,
        patient_name: name, patient_phone: phone, reason,
      }),
    }).then(r => r.json());

    _bkUpdateSteps();
    body.innerHTML = `
      <div style="text-align:center;padding:32px 16px">
        <div style="font-size:52px;margin-bottom:16px">✅</div>
        <h3 style="font-size:17px;color:var(--success);margin-bottom:20px">Đặt lịch thành công!</h3>
        <div class="bk-summary" style="text-align:left">
          <strong>${_bkData.dept_name}</strong><br>
          ${_bkData.doctor_name}<br>
          📅 ${_bkData.date} &nbsp;⏰ ${_bkData.start_time} – ${_bkData.end_time}<br>
          👤 ${name}${phone ? ' · ' + phone : ''}
        </div>
        <button class="bk-submit" style="margin-top:12px" onclick="closeBooking()">Đóng</button>
      </div>`;
  } catch(e) {
    body.innerHTML = `<p style="color:var(--danger);padding:20px">Lỗi đặt lịch: ${e.message}</p>
      <button class="bk-back" onclick="_bkStep=4;_bkRenderStep()">← Thử lại</button>`;
  }
}

/* ══════════════════════════════════════
   PATIENT SEARCH MODAL
══════════════════════════════════════ */
function openSearch() {
  document.getElementById('search-overlay').classList.remove('hidden');
  document.getElementById('srch-results').innerHTML = '';
  const inp = document.getElementById('srch-input');
  inp.value = '';
  setTimeout(() => inp.focus(), 80);
}
function closeSearch() {
  document.getElementById('search-overlay').classList.add('hidden');
}

async function _doSearch() {
  const q = document.getElementById('srch-input').value.trim();
  if (!q) return;
  const area = document.getElementById('srch-results');
  area.innerHTML = '<div class="srch-empty">Đang tìm kiếm…</div>';
  try {
    const data = await fetch(`/api/patients?q=${encodeURIComponent(q)}&_count=20`).then(r => r.json());
    const pts = data.patients || [];
    if (!pts.length) {
      area.innerHTML = '<div class="srch-empty">Không tìm thấy bệnh nhân.</div>';
      return;
    }
    area.innerHTML = pts.map(p => `
      <div class="srch-result" onclick="_showPatient('${p.id}')">
        <div class="srch-result-name">${p.name}</div>
        <div class="srch-result-sub">
          ${p.phone || ''}${p.birth_date ? ' · ' + p.birth_date : ''}${p.gender ? ' · ' + p.gender : ''}
        </div>
      </div>`).join('');
  } catch(e) {
    area.innerHTML = `<div class="srch-empty" style="color:var(--danger)">Lỗi: ${e.message}</div>`;
  }
}

async function _showPatient(id) {
  const area = document.getElementById('srch-results');
  area.innerHTML = '<div class="srch-empty">Đang tải hồ sơ…</div>';
  try {
    const p = await fetch(`/api/patient/${id}`).then(r => r.json());
    const appts = p.appointments || [];

    const apptRows = appts.slice(0,5).map(a =>
      `<tr><td style="padding:4px 8px 4px 0">${a.start||''}</td><td style="padding:4px 8px">${a.department||''}</td><td style="padding:4px 0;color:var(--text-02)">${a.status||''}</td></tr>`
    ).join('');

    area.innerHTML = `
      <div class="pt-back" onclick="_doSearch()">← Quay lại kết quả</div>
      <div class="pt-card">
        <div class="pt-card-name">👤 ${p.name || 'Không rõ tên'}</div>
        <div class="pt-card-grid">
          <div class="pt-card-field"><label>Ngày sinh</label><span>${p.birth_date || '—'}</span></div>
          <div class="pt-card-field"><label>Giới tính</label><span>${p.gender || '—'}</span></div>
          <div class="pt-card-field"><label>Số điện thoại</label><span>${p.phone || '—'}</span></div>
          <div class="pt-card-field"><label>Mã BN</label><span>${p.id || '—'}</span></div>
        </div>
        ${appts.length ? `
        <div class="bk-label" style="margin-top:12px">Lịch sử khám gần đây</div>
        <table style="width:100%;font-size:12px;border-collapse:collapse">${apptRows}</table>` : ''}
      </div>`;
  } catch(e) {
    area.innerHTML = `<div class="srch-empty" style="color:var(--danger)">Lỗi: ${e.message}</div>`;
  }
}

/* ══════════════════════════════════════
   DEPARTMENTS MODAL
══════════════════════════════════════ */
async function openDepts() {
  document.getElementById('dept-overlay').classList.remove('hidden');
  const body = document.getElementById('dept-body');
  body.innerHTML = '<div class="bk-loading">Đang tải…</div>';
  try {
    const data = await fetch('/api/departments').then(r => r.json());
    const depts = data.departments || [];
    if (!depts.length) {
      body.innerHTML = '<div class="bk-loading">Không có khoa nào.</div>';
      return;
    }
    body.innerHTML = `<div class="dept-grid">${
      depts.map(d => `
        <div class="dept-card" onclick="closeDepts();openBooking();_bkSelectDept('${d.code}','${(d.display||d.code).replace(/'/g,"\\'")}')">
          <div class="dept-card-icon">${_DEPT_ICONS[d.code] || '🏥'}</div>
          <div class="dept-card-name">${d.display || _DEPT_NAMES[d.code] || d.code}</div>
          <div class="dept-card-count">${d.schedule_count || ''} bác sĩ</div>
        </div>`).join('')
    }</div>`;
  } catch(e) {
    body.innerHTML = `<div class="bk-loading" style="color:var(--danger)">Lỗi: ${e.message}</div>`;
  }
}
function closeDepts() {
  document.getElementById('dept-overlay').classList.add('hidden');
}

/* ══════════════════════════════════════
   REGISTER PATIENT MODAL
══════════════════════════════════════ */
function openRegister() {
  document.getElementById('register-overlay').classList.remove('hidden');
  _regRenderForm();
}
function closeRegister() {
  document.getElementById('register-overlay').classList.add('hidden');
}

function _regRenderForm() {
  document.getElementById('register-body').innerHTML = `
    <div class="reg-form">
      <div class="reg-row">
        <div class="reg-field">
          <div class="reg-label">Họ và tên *</div>
          <input id="reg-name" class="reg-input" type="text" placeholder="Nguyễn Văn A">
        </div>
        <div class="reg-field">
          <div class="reg-label">Giới tính *</div>
          <select id="reg-gender" class="reg-select">
            <option value="">-- Chọn --</option>
            <option value="male">Nam</option>
            <option value="female">Nữ</option>
            <option value="other">Khác</option>
          </select>
        </div>
      </div>
      <div class="reg-row">
        <div class="reg-field">
          <div class="reg-label">Ngày sinh *</div>
          <input id="reg-dob" class="reg-input" type="date" max="${new Date().toISOString().slice(0,10)}">
        </div>
        <div class="reg-field">
          <div class="reg-label">Số điện thoại</div>
          <input id="reg-phone" class="reg-input" type="tel" placeholder="09xx xxx xxx">
        </div>
      </div>
      <div class="reg-field">
        <div class="reg-label">Địa chỉ</div>
        <input id="reg-addr" class="reg-input" type="text" placeholder="Số nhà, đường, quận, thành phố">
      </div>
    </div>
    <button class="reg-submit" id="reg-btn" onclick="_regSubmit()">Đăng ký →</button>`;
  setTimeout(() => document.getElementById('reg-name').focus(), 80);
}

async function _regSubmit() {
  const name   = document.getElementById('reg-name').value.trim();
  const gender = document.getElementById('reg-gender').value;
  const dob    = document.getElementById('reg-dob').value;
  const phone  = document.getElementById('reg-phone').value.trim();
  const addr   = document.getElementById('reg-addr').value.trim();

  let ok = true;
  ['reg-name','reg-gender','reg-dob'].forEach(id => {
    const el = document.getElementById(id);
    if (!el.value.trim()) { el.classList.add('err'); ok = false; }
    else el.classList.remove('err');
  });
  if (!ok) return;

  const btn = document.getElementById('reg-btn');
  btn.disabled = true; btn.textContent = 'Đang đăng ký…';

  try {
    const res = await fetch('/api/register-patient', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ name, gender, birth_date: dob, phone, address: addr }),
    }).then(r => r.json());

    document.getElementById('register-body').innerHTML = `
      <div class="reg-success">
        <div class="reg-success-icon">✅</div>
        <div class="reg-success-msg">Đăng ký thành công!</div>
        <div class="reg-success-sub">Mã bệnh nhân: <strong>${res.patient_id}</strong></div>
        <div class="bk-summary" style="text-align:left;margin:0 auto;max-width:320px">
          👤 ${name}<br>
          ${dob ? '🎂 ' + dob + '<br>' : ''}
          ${phone ? '📞 ' + phone + '<br>' : ''}
          ${addr ? '📍 ' + addr : ''}
        </div>
        <button class="reg-submit" style="margin-top:20px;max-width:200px" onclick="_regRenderForm()">Đăng ký thêm</button>
        <button class="bk-submit" style="margin-top:10px;background:var(--ui-03);color:var(--text-01);max-width:200px" onclick="closeRegister()">Đóng</button>
      </div>`;
  } catch(e) {
    btn.disabled = false; btn.textContent = 'Đăng ký →';
    alert('Lỗi đăng ký: ' + e.message);
  }
}

/* ══════════════════════════════════════════
   TOAST
══════════════════════════════════════════ */
let _toastTimer = null;
function showToast(msg, durationMs = 3000) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.remove('show'), durationMs);
}

/* ══════════════════════════════════════════
   PENDING APPOINTMENTS (doctor only)
══════════════════════════════════════════ */
let _pendingPollInterval = null;
let _pendingPanelOpen    = false;

function _setPendingBadge(count) {
  const badge       = document.getElementById('pending-badge');
  const panelCount  = document.getElementById('pending-panel-count');
  if (!badge || !panelCount) return;
  if (count > 0) {
    badge.textContent      = count > 99 ? '99+' : count;
    panelCount.textContent = count > 99 ? '99+' : count;
    badge.classList.remove('hidden');
    panelCount.classList.remove('hidden');
  } else {
    badge.classList.add('hidden');
    panelCount.classList.add('hidden');
  }
}

async function fetchPendingAppointments() {
  if (role !== 'doctor') return;
  try {
    const data = await fetch('/api/pending-appointments').then(r => r.json());
    const appts = data.appointments || [];
    _setPendingBadge(appts.length);
    if (_pendingPanelOpen) {
      _renderPendingList(appts);
    }
  } catch { /* silently ignore poll errors */ }
}

function _renderPendingList(appts) {
  const body = document.getElementById('pending-panel-body');
  if (!body) return;
  if (!appts.length) {
    body.innerHTML = '<div class="pending-empty">Không có lịch hẹn nào đang chờ xác nhận.</div>';
    return;
  }
  body.innerHTML = appts.map(a => {
    const dateStr = a.start
      ? a.start.slice(0, 10).split('-').reverse().join('/') + ' ' + (a.start.slice(11, 16) || '')
      : '—';
    const safeId = (a.id || '').replace(/'/g, '');
    return `
      <div class="pending-item" id="pending-item-${safeId}">
        <div class="pending-item-row">
          <span class="pending-item-name">${a.patient_name || '—'}</span>
          <span class="badge badge-yellow" style="margin-left:auto">Chờ xác nhận</span>
        </div>
        <div class="pending-item-meta">🏥 ${a.department || '—'} &nbsp;·&nbsp; 📅 ${dateStr}</div>
        ${a.reason ? `<div class="pending-item-note">📋 ${a.reason}</div>` : ''}
        ${a.patient_email ? `<div class="pending-item-email">✉ ${a.patient_email}</div>` : ''}
        <div class="pending-item-actions">
          <button class="pending-confirm-btn" onclick="confirmAppointment('${safeId}', this)">✓ Xác nhận</button>
          <button class="pending-reject-btn"  onclick="rejectAppointment('${safeId}', this)">✗ Từ chối</button>
        </div>
      </div>`;
  }).join('');
}

function togglePendingPanel() {
  if (role !== 'doctor') return;
  _pendingPanelOpen = !_pendingPanelOpen;
  const body     = document.getElementById('pending-panel-body');
  const chevron  = document.getElementById('pending-panel-chevron');
  const header   = document.getElementById('pending-panel-header');
  if (!body) return;
  body.classList.toggle('open', _pendingPanelOpen);
  chevron?.classList.toggle('open', _pendingPanelOpen);
  header?.classList.toggle('open', _pendingPanelOpen);
  if (_pendingPanelOpen) {
    fetchPendingAppointments();
  }
}

function _disableRowBtns(btn) {
  const row = btn.closest('tr') || btn.closest('.pending-item-actions');
  if (row) row.querySelectorAll('button').forEach(b => b.disabled = true);
  else btn.disabled = true;
}
function _enableRowBtns(btn) {
  const row = btn.closest('tr') || btn.closest('.pending-item-actions');
  if (row) row.querySelectorAll('button').forEach(b => b.disabled = false);
  else btn.disabled = false;
}

// ── Complete appointment (Kết thúc khám) ──
let _completeApptId = '', _completePatientId = '';

async function fetchAISuggestion() {
  const btn = document.getElementById('ai-suggest-btn');
  const errEl = document.getElementById('complete-error');
  errEl.style.display = 'none';
  btn.disabled = true;
  btn.textContent = '⏳ Đang gợi ý...';
  try {
    const res = await fetch('/api/suggest-completion', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        patient_id:     _completePatientId,
        appointment_id: _completeApptId,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const data = await res.json();
    if (data.diagnosis) document.getElementById('complete-diagnosis').value = data.diagnosis;
    if (data.notes)     document.getElementById('complete-notes').value     = data.notes;
    if (data.plan)      document.getElementById('complete-plan').value      = data.plan;
  } catch (e) {
    errEl.textContent = 'Gợi ý thất bại: ' + e.message;
    errEl.style.display = 'block';
  } finally {
    btn.disabled = false;
    btn.textContent = '✨ AI gợi ý';
  }
}

async function openCompleteModal(apptId, patientId, patientName) {
  _completeApptId   = apptId;
  _completePatientId = patientId;
  // Reuse rx state cho medication rows
  _rxModalPatientId   = patientId;
  _rxModalPatientName = patientName;
  _rxMedRows          = {};
  _rxMedRowSeq        = 0;
  document.getElementById('complete-patient-label').textContent = `Bệnh nhân: ${patientName}`;
  document.getElementById('complete-diagnosis').value = '';
  document.getElementById('complete-notes').value = '';
  document.getElementById('complete-plan').value = '';
  document.getElementById('complete-medications-list').innerHTML = '';
  document.getElementById('complete-error').style.display = 'none';
  document.getElementById('complete-allergy-banner').style.display = 'none';
  document.getElementById('complete-send-email').checked = true;
  document.getElementById('complete-patient-email').value = '';
  document.getElementById('complete-overlay').classList.remove('hidden');
  setTimeout(() => document.getElementById('complete-diagnosis').focus(), 100);

  // Auto-load email từ FHIR Patient.telecom
  try {
    const r = await fetch('/api/patient/' + patientId);
    if (r.ok) {
      const p = await r.json();
      if (p.email) document.getElementById('complete-patient-email').value = p.email;
    }
  } catch (e) { /* silently ignore */ }

  // Load drug catalog + allergies trong background
  if (!_rxDrugCatalog) {
    try {
      const r = await fetch('/api/drug-catalog');
      const d = await r.json();
      _rxDrugCatalog = d.by_category;
    } catch (e) { _rxDrugCatalog = {}; }
  }
  try {
    const r = await fetch('/api/allergies/' + patientId);
    const d = await r.json();
    _rxAllergies = d.allergies || [];
  } catch (e) { _rxAllergies = []; }

  // TIER 1: Render allergy banner
  const banner = document.getElementById('complete-allergy-banner');
  const medAllergies = _rxAllergies.filter(a => a.category === 'medication');
  if (medAllergies.length) {
    const items = medAllergies.map(a => {
      const icon = a.criticality === 'high' ? '🚨' : '⚠';
      const sev = a.severity_vi || '';
      return `<li>${icon} <strong>${a.substance}</strong> ${sev ? '— ' + sev : ''} ${a.reaction ? '(' + a.reaction + ')' : ''}</li>`;
    }).join('');
    banner.style.display = 'block';
    banner.innerHTML = `
      <div class="rx-allergy-title">🚨 DỊ ỨNG THUỐC ĐÃ GHI NHẬN</div>
      <ul>${items}</ul>
    `;
  }
}

function closeCompleteModal() {
  document.getElementById('complete-overlay').classList.add('hidden');
}

async function submitCompleteAppt() {
  const diagnosis = document.getElementById('complete-diagnosis').value.trim();
  const notes     = document.getElementById('complete-notes').value.trim();
  const plan      = document.getElementById('complete-plan').value.trim();
  const errEl     = document.getElementById('complete-error');
  const btn       = document.getElementById('complete-submit-btn');

  errEl.style.display = 'none';

  // ── Collect + validate medications từ _rxMedRows ──
  const meds = [];
  let hasUnresolved = false;
  for (const [rowId, state] of Object.entries(_rxMedRows)) {
    const row = document.getElementById(rowId);
    if (!row) continue;
    const drugId = row.querySelector('.rx-drug-select').value;
    if (!drugId) continue;

    const dose = parseFloat(row.querySelector('.rx-dose').value) || 1;
    const freq = parseInt(row.querySelector('.rx-freq').value) || 1;
    const dur  = parseInt(row.querySelector('.rx-dur').value)  || null;
    const instr = row.querySelector('.rx-instr').value.trim();

    const med = {
      drug_id: drugId,
      dose_per_intake: dose,
      frequency_per_day: freq,
      duration_days: dur,
      instructions: instr,
    };
    // TIER 3: chặn nếu có critical chưa override
    if (state.checkResult && state.checkResult.verdict === 'block') {
      if (!state.overrideReason || state.overrideReason.length < 5) {
        hasUnresolved = true;
        row.classList.add('rx-row-error');
        continue;
      }
      med.override_reason = state.overrideReason;
    }
    meds.push(med);
  }
  if (hasUnresolved) {
    errEl.innerHTML = '🚨 Đơn có thuốc bị chặn do dị ứng. Đổi thuốc hoặc nhập lý do override (≥5 ký tự).';
    errEl.style.display = 'block';
    return;
  }

  // Diagnosis bắt buộc nếu có kê thuốc (cho prescription.reason)
  if (meds.length && !diagnosis) {
    errEl.textContent = 'Cần nhập chẩn đoán khi kê thuốc.';
    errEl.style.display = 'block';
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Đang lưu...';

  try {
    // ── Step 1: Complete appointment (lưu ClinicalImpression + đổi status + email) ──
    const sendEmail    = document.getElementById('complete-send-email').checked;
    const patientEmail = document.getElementById('complete-patient-email').value.trim();
    // Build medication snapshot cho email (drug_name + instruction) từ catalog
    const emailMeds = meds.map(m => {
      const drug = _rxDrugCatalog
        ? Object.values(_rxDrugCatalog).flat().find(d => d.id === m.drug_id)
        : null;
      const drugName = drug ? `${drug.name} ${drug.strength}` : m.drug_id;
      const dur = m.duration_days ? ` × ${m.duration_days} ngày` : '';
      const instr = m.instructions ? ` (${m.instructions})` : '';
      return {
        drug_name:   drugName,
        instruction: `${m.dose_per_intake} ${drug?.form || 'viên'} × ${m.frequency_per_day} lần/ngày${dur}${instr}`,
      };
    });
    const r1 = await fetch(`/api/complete-appointment/${_completeApptId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        patient_id:      _completePatientId,
        practitioner_id: currentDoctor?.id || '',
        diagnosis, notes, plan,
        send_email:      sendEmail && !!patientEmail,
        patient_email:   patientEmail,
        medications:     emailMeds,
      }),
    });
    if (!r1.ok) {
      const err = await r1.json().catch(() => ({}));
      throw new Error('Kết thúc khám: ' + (err.detail || `HTTP ${r1.status}`));
    }

    // ── Step 2: Kê đơn (nếu có thuốc) ──
    let rxResult = null;
    if (meds.length) {
      const r2 = await fetch('/api/prescription', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          patient_id:      _completePatientId,
          practitioner_id: currentDoctor?.id || 'unknown-doctor',
          diagnosis,
          medications:     meds,
        }),
      });
      const rxD = await r2.json();
      if (!r2.ok) throw new Error('Kê đơn: ' + (rxD.detail || `HTTP ${r2.status}`));
      if (rxD.saved === false && rxD.error === 'prescription_blocked') {
        errEl.innerHTML = '🚨 Server từ chối đơn thuốc: ' + rxD.message;
        errEl.style.display = 'block';
        return;
      }
      rxResult = rxD;
    }

    closeCompleteModal();
    loadAppointments();
    // r1 result có thể chứa email field
    const r1Data  = await r1.clone().json().catch(() => ({}));
    const emailOk = r1Data.email && r1Data.email.success;
    const emailLine = emailOk ? ' · 📧 Email đã gửi' : (r1Data.email?.error ? ' · ⚠ Email lỗi' : '');
    const summary = rxResult
      ? `✅ Đã kết thúc khám — chẩn đoán + ${rxResult.medications.length} thuốc${emailLine}`
      : `✅ Đã kết thúc khám và lưu ghi chú lâm sàng${emailLine}`;
    showToast(summary);
    openPatientPanel(_completePatientId, 'notes');
  } catch (e) {
    errEl.textContent = 'Lỗi: ' + e.message;
    errEl.style.display = 'block';
  } finally {
    btn.disabled = false;
    btn.textContent = '✅ Lưu & Kết thúc khám';
  }
}

async function confirmAppointment(id, btn) {
  _disableRowBtns(btn);
  try {
    const res = await fetch(`/api/confirm-appointment/${id}`, { method: 'POST' });
    const data = await res.json();
    if (!res.ok) { showToast('Lỗi: ' + (data.detail || res.status)); _enableRowBtns(btn); return; }
    showToast('Đã xác nhận và gửi mail cho bệnh nhân');
    _refreshPendingPanel();
    await loadAppointments();
  } catch(e) {
    showToast('Lỗi xác nhận: ' + e.message);
    _enableRowBtns(btn);
  }
}

async function rejectAppointment(id, btn) {
  _disableRowBtns(btn);
  try {
    const res = await fetch(`/api/reject-appointment/${id}`, { method: 'POST' });
    const data = await res.json();
    if (!res.ok) { showToast('Lỗi: ' + (data.detail || res.status)); _enableRowBtns(btn); return; }
    showToast('Đã từ chối lịch hẹn');
    _refreshPendingPanel();
    await loadAppointments();
  } catch(e) {
    showToast('Lỗi từ chối: ' + e.message);
    _enableRowBtns(btn);
  }
}

function openApptDetail(id) {
  const appt = (window._apptData || []).find(a => a.id === id);
  if (!appt) { showToast('Không tìm thấy lịch hẹn'); return; }
  const time = appt.start ? appt.start.replace('T', ' ').slice(0, 16) : '—';
  alert(`Lịch hẹn: ${appt.patient_name || '—'}\nGiờ: ${time}\nKhoa: ${appt.department || '—'}\nBác sĩ: ${appt.practitioner || '—'}\nTrạng thái: ${appt.status}\nLý do: ${appt.reason || '—'}`);
}

async function _refreshPendingPanel() {
  try {
    const data = await fetch('/api/pending-appointments').then(r => r.json());
    const appts = data.appointments || [];
    _setPendingBadge(appts.length);
    if (_pendingPanelOpen) _renderPendingList(appts);
  } catch { /* ignore */ }
}

function _startPendingPoll() {
  fetchPendingAppointments();
  clearInterval(_pendingPollInterval);
  _pendingPollInterval = setInterval(fetchPendingAppointments, 30000);
}

function _stopPendingPoll() {
  clearInterval(_pendingPollInterval);
  _pendingPollInterval = null;
  _setPendingBadge(0);
  _pendingPanelOpen = false;
  const body    = document.getElementById('pending-panel-body');
  const chevron = document.getElementById('pending-panel-chevron');
  const header  = document.getElementById('pending-panel-header');
  body?.classList.remove('open');
  chevron?.classList.remove('open');
  header?.classList.remove('open');
}

/* ─── Lab CBC Picker ─── */

function openLabCbcPicker() {
  const picker = document.getElementById('lab-cbc-picker');
  if (!picker) return;
  picker.classList.remove('hidden');
  document.getElementById('lab-cbc-search')?.focus();
}

function closeLabCbcPicker() {
  const picker = document.getElementById('lab-cbc-picker');
  if (!picker) return;
  picker.classList.add('hidden');
  const input = document.getElementById('lab-cbc-search');
  if (input) input.value = '';
  const results = document.getElementById('lab-cbc-results');
  if (results) results.innerHTML = '';
}

let _labCbcSearchTimer = null;
async function searchLabCbcPatient() {
  clearTimeout(_labCbcSearchTimer);
  _labCbcSearchTimer = setTimeout(async () => {
    const q = document.getElementById('lab-cbc-search')?.value?.trim();
    const results = document.getElementById('lab-cbc-results');
    if (!results) return;
    if (!q || q.length < 2) { results.innerHTML = ''; return; }
    results.innerHTML = '<div style="font-size:12px;color:var(--text-03);padding:4px 0">Đang tìm...</div>';
    try {
      const data = await fetch(`/api/patients?_count=10&q=${encodeURIComponent(q)}`).then(r => r.json());
      const rows = data.patients || [];
      if (!rows.length) {
        results.innerHTML = '<div style="font-size:12px;color:var(--text-03);padding:4px 0">Không tìm thấy</div>';
        return;
      }
      results.innerHTML = rows.map(p => `
        <div class="lab-cbc-patient-row" onclick="selectLabCbcPatient('${p.id}','${(p.name||'').replace(/'/g,"&#39;")}')">
          <strong>${p.name || '—'}</strong>
          <span>${p.gender || ''} · ${p.birth_date ? p.birth_date.split('-').reverse().join('/') : '—'} · ${p.phone || ''}</span>
        </div>`).join('');
    } catch (e) {
      results.innerHTML = `<div style="font-size:12px;color:var(--danger);padding:4px 0">Lỗi: ${e.message}</div>`;
    }
  }, 300);
}

function selectLabCbcPatient(patientId, patientName) {
  closeLabCbcPicker();
  openCbcModal(patientId, patientName);
}
