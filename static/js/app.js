(function () {
  'use strict';

  const tabBtns     = document.querySelectorAll('.tab-btn');
  const panes       = document.querySelectorAll('.tab-pane');
  const emailInput  = document.getElementById('email-input');
  const verifyBtn   = document.getElementById('verify-btn');
  const resultPanel = document.getElementById('result-panel');
  const bulkInput   = document.getElementById('bulk-input');
  const bulkBtn     = document.getElementById('bulk-btn');
  const downloadBtn = document.getElementById('download-btn');
  const bulkResults = document.getElementById('bulk-results');
  let bulkData = null;

  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const t = btn.dataset.tab;
      tabBtns.forEach(b => {
        b.classList.toggle('tab-btn--active', b.dataset.tab === t);
        b.setAttribute('aria-selected', b.dataset.tab === t ? 'true' : 'false');
      });
      panes.forEach(p => p.classList.toggle('tab-pane--active', p.id === `pane-${t}`));
    });
  });

  async function doVerify() {
    const email = emailInput.value.trim();
    if (!email) { emailInput.focus(); return; }
    setLoading(resultPanel);
    verifyBtn.disabled = true;
    try {
      const res = await fetch('/verify', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email }) });
      resultPanel.innerHTML = renderCard(await res.json());
    } catch { resultPanel.innerHTML = renderError('Network error.'); }
    finally { verifyBtn.disabled = false; }
  }

  verifyBtn.addEventListener('click', doVerify);
  emailInput.addEventListener('keydown', e => { if (e.key === 'Enter') doVerify(); });

  bulkBtn.addEventListener('click', async () => {
    const emails = bulkInput.value.trim().split('\n').map(s => s.trim()).filter(Boolean);
    if (!emails.length) { bulkInput.focus(); return; }
    if (emails.length > 100) { bulkResults.innerHTML = renderError('Max 100 addresses.'); return; }
    bulkBtn.disabled = true; downloadBtn.disabled = true; bulkData = null;
    setLoading(bulkResults, `Verifying ${emails.length} address${emails.length !== 1 ? 'es' : ''}...`);
    try {
      const res = await fetch('/bulk', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ emails }) });
      const data = await res.json();
      if (!Array.isArray(data)) { bulkResults.innerHTML = renderError(data.error || 'Error.'); return; }
      bulkData = data; bulkResults.innerHTML = renderTable(data); downloadBtn.disabled = false;
    } catch { bulkResults.innerHTML = renderError('Network error.'); }
    finally { bulkBtn.disabled = false; }
  });

  downloadBtn.addEventListener('click', () => {
    if (!bulkData) return;
    const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(new Blob([toCSV(bulkData)], { type: 'text/csv' })), download: 'results.csv' });
    a.click();
  });

  function setLoading(el, msg = 'Verifying...') { el.innerHTML = `<div class="result-loading"><div class="spinner"></div><span>${esc(msg)}</span></div>`; }
  function renderCard(d) {
    const b = [d.is_disposable ? '<span class="badge badge--disposable">Disposable</span>' : '', d.is_role_based ? '<span class="badge badge--role">Role address</span>' : '', d.catch_all ? '<span class="badge badge--catchall">Catch-all</span>' : ''].join('');
    return `<div class="result-card result-card--${d.color||'gray'}"><p class="result-status">${label(d.status)}</p><p class="result-email">${esc(d.email)}</p><p class="result-detail">${esc(d.details||'')}</p>${b ? `<div class="result-badges">${b}</div>` : ''}${d.smtp_code!=null ? `<p class="result-smtp">${esc(String(d.smtp_code))} ${esc(d.smtp_msg||'')}</p>' : ''}</div>`;
  }
  function renderTable(rows) {
    return `<table class="bulk-table"><thead><tr><th>Address</th><th>Status</th><th>Details</th></tr></thead><tbody>${rows.map(r => `<tr><td style="word-break:break-all">${esc(r.email)}</td><td><span class="status-pill status-pill--${r.color||'gray'}">${label(r.status)}</span></td><td class="bulk-detail-text">${esc(r.details||'')}</td></tr>`).join('')}</tbody></table>`;
  }
  function renderError(m) { return `<div class="result-card result-card--gray"><p class="result-status">Error</p><p class="result-detail">${esc(m)}</p></div>`; }
  function toCSV(r) { const h = ['email','status','details','is_disposable','is_role_based','catch_all','smtp_code','smtp_msg','mx_records']; return [h.join(','), ...r.map(x => [x.email,x.status,x.details,x.is_disposable,x.is_role_based,x.catch_all??'',x.smtp_code??'',x.smtp_msg||'',(x.mx_records||[]).join('; ')].map(v => { const s=String(v??''); return s.match(/[,"\n]/)?`"${s.replace(/"/g,'""')}"`:s; }).join(','))].join('\r\n'); }
  function label(s) { return {valid:'Valid',invalid:'Invalid',unverifiable:'Unverifiable',error:'Error'}[s]||s; }
  function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
})();
