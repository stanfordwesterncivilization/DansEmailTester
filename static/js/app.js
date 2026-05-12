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

  // ── Tabs ──────────────────────────────────────────────────
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

  // ── Single verify ───────────────────────────────────────────
  async function doVerify() {
    const email = emailInput.value.trim();
    if (!email) { emailInput.focus(); return; }
    setLoading(resultPanel);
    verifyBtn.disabled = true;
    try {
      const res  = await fetch('/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email })
      });
      const data = await res.json();
      resultPanel.innerHTML = renderCard(data);
    } catch (e) {
      resultPanel.innerHTML = renderError('Network error.');
    } finally {
      verifyBtn.disabled = false;
    }
  }

  verifyBtn.addEventListener('click', doVerify);
  emailInput.addEventListener('keydown', e => { if (e.key === 'Enter') doVerify(); });

  // ── Bulk verify ─────────────────────────────────────────────
  bulkBtn.addEventListener('click', async () => {
    const emails = bulkInput.value.trim().split('\n').map(s => s.trim()).filter(Boolean);
    if (!emails.length) { bulkInput.focus(); return; }
    if (emails.length > 100) { bulkResults.innerHTML = renderError('Max 100 addresses.'); return; }
    bulkBtn.disabled = true;
    downloadBtn.disabled = true;
    bulkData = null;
    setLoading(bulkResults, `Verifying ${emails.length} address${emails.length !== 1 ? 'es' : ''}...`);
    try {
      const res  = await fetch('/bulk', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ emails })
      });
      const data = await res.json();
      if (!Array.isArray(data)) { bulkResults.innerHTML = renderError(data.error || 'Error.'); return; }
      bulkData = data;
      bulkResults.innerHTML = renderTable(data);
      downloadBtn.disabled  = false;
    } catch (e) {
      bulkResults.innerHTML = renderError('Network error.');
    } finally {
      bulkBtn.disabled = false;
    }
  });

  downloadBtn.addEventListener('click', () => {
    if (!bulkData) return;
    const blob = new Blob([toCSV(bulkData)], { type: 'text/csv' });
    const a = Object.assign(document.createElement('a'), {
      href: URL.createObjectURL(blob), download: 'results.csv'
    });
    a.click();
  });

  // ── Render ──────────────────────────────────────────────────
  function setLoading(el, msg = 'Verifying...') {
    el.innerHTML = `<div class="result-loading"><div class="spinner"></div><span>${esc(msg)}</span></div>`;
  }

  function renderCard(d) {
    const badges = [
      d.is_disposable ? `<span class="badge badge--disposable">Disposable</span>` : '',
      d.is_role_based  ? `<span class="badge badge--role">Role address</span>`    : '',
      d.catch_all      ? `<span class="badge badge--catchall">Catch-all</span>`   : '',
    ].join('');
    const smtp = d.smtp_code != null
      ? `<p class="result-smtp">${esc(String(d.smtp_code))} ${esc(d.smtp_msg || '')}</p>`
      : '';
    return `<div class="result-card result-card--${d.color || 'gray'}">
      <p class="result-status">${label(d.status)}</p>
      <p class="result-email">${esc(d.email)}</p>
      <p class="result-detail">${esc(d.details || '')}</p>
      ${badges ? `<div class="result-badges">${badges}</div>` : ''}
      ${smtp}
    </div>`;
  }

  function renderTable(rows) {
    const trs = rows.map(r => `<tr>
      <td style="word-break:break-all">${esc(r.email)}</td>
      <td><span class="status-pill status-pill--${r.color || 'gray'}">${label(r.status)}</span></td>
      <td class="bulk-detail-text">${esc(r.details || '')}</td>
    </tr>`).join('');
    return `<table class="bulk-table">
      <thead><tr><th>Address</th><th>Status</th><th>Details</th></tr></thead>
      <tbody>${trs}</tbody>
    </table>`;
  }

  function renderError(msg) {
    return `<div class="result-card result-card--gray"><p class="result-status">Error</p><p class="result-detail">${esc(msg)}</p></div>`;
  }

  function toCSV(results) {
    const h = ['email','status','details','is_disposable','is_role_based','catch_all','smtp_code','smtp_msg','mx_records'];
    const lines = [h.join(',')];
    for (const r of results) lines.push([
      csvCell(r.email), csvCell(r.status), csvCell(r.details),
      csvCell(r.is_disposable), csvCell(r.is_role_based),
      csvCell(r.catch_all ?? ''), csvCell(r.smtp_code ?? ''),
      csvCell(r.smtp_msg || ''), csvCell((r.mx_records||[]).join('; '))
    ].join(','));
    return lines.join('\r\n');
  }

  function label(s) {
    return { valid:'Valid', invalid:'Invalid', unverifiable:'Unverifiable', error:'Error' }[s] || s;
  }
  function csvCell(v) {
    const s = String(v ?? '');
    return (s.includes(',') || s.includes('"') || s.includes('\n'))
      ? `"${s.replace(/"/g,'""')}"` : s;
  }
  function esc(str) {
    return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }
})();
