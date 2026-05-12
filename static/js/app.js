(function () {
  'use strict';

  const emailInput  = document.getElementById('email-input');
  const verifyBtn   = document.getElementById('verify-btn');
  const resultPanel = document.getElementById('result-panel');

  // ── Verify ─────────────────────────────────────────────────
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
      resultPanel.innerHTML = renderError('Network error — please try again.');
    } finally {
      verifyBtn.disabled = false;
    }
  }

  verifyBtn.addEventListener('click', doVerify);
  emailInput.addEventListener('keydown', function (e) { if (e.key === 'Enter') doVerify(); });

  // ── Render ──────────────────────────────────────────────────
  function setLoading(el) {
    el.innerHTML = '<div class="result-loading"><div class="spinner"></div><span>Verifying...</span></div>';
  }

  function renderCard(d) {
    const badges = [
      d.is_disposable ? '<span class="badge badge--disposable">Disposable</span>' : '',
      d.is_role_based  ? '<span class="badge badge--role">Role address</span>'    : '',
      d.catch_all      ? '<span class="badge badge--catchall">Catch-all</span>'   : '',
    ].join('');
    return '<div class="result-card result-card--' + (d.color || 'gray') + '">' +
      '<p class="result-status">' + label(d.status) + '</p>' +
      '<p class="result-email">'  + esc(d.email)    + '</p>' +
      '<p class="result-detail">' + esc(d.details || '') + '</p>' +
      (badges ? '<div class="result-badges">' + badges + '</div>' : '') +
    '</div>';
  }

  function renderError(msg) {
    return '<div class="result-card result-card--gray"><p class="result-status">Error</p><p class="result-detail">' + esc(msg) + '</p></div>';
  }

  function label(s) {
    return { valid: 'Valid', invalid: 'Invalid', unverifiable: 'Unverifiable', error: 'Error' }[s] || s;
  }

  function esc(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }
})();
