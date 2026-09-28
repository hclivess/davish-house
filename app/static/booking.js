// Check-in / check-out picker with live availability check and quote (hourly resolution, any length of stay).
(function () {
  const panel = document.getElementById('book');
  const form = document.getElementById('book-form');
  if (!panel || !form) return;
  const T = JSON.parse(panel.dataset.i18n || '{}'); const t = k => T[k] || k;
  const listingId = Number(panel.dataset.listing);
  const minH = parseFloat(panel.dataset.min) || 1;
  const startIn = document.getElementById('start_at'), endIn = document.getElementById('end_at');
  const selEl = document.getElementById('selection'), quoteEl = document.getElementById('quote'), btn = document.getElementById('book-btn');
  const cur = panel.dataset.currency && panel.dataset.currency !== 'USD' ? ' ' + panel.dataset.currency : '';
  const money = c => '$' + (c / 100).toLocaleString(undefined, { minimumFractionDigits: c % 100 ? 2 : 0, maximumFractionDigits: 2 }) + cur;
  const guestsIn = document.getElementById('guests');
  const plural = (n, one, many) => `${n} ${n === 1 ? t(one) : t(many)}`;
  const duration = h => { const d = Math.floor(h / 24), r = Math.round(h - d * 24); return (d ? plural(d, 'day', 'days') : '') + (d && r ? ' ' : '') + (r || !d ? plural(r, 'hour', 'hours') : ''); };
  let seq = 0;

  function snap(el) { // force whole hours
    if (!el.value) return;
    const [d, tm] = el.value.split('T'); if (!tm) return;
    el.value = `${d}T${tm.slice(0, 2)}:00`;
  }

  let update = async function () {
    snap(startIn); snap(endIn);
    quoteEl.hidden = true; if (btn) btn.disabled = true;
    if (!startIn.value || !endIn.value) { selEl.textContent = ''; return; }
    if (endIn.value <= startIn.value) { selEl.innerHTML = `<span class="err">${t('Check-out must be after check-in.')}</span>`; return; }
    const hours = (new Date(endIn.value) - new Date(startIn.value)) / 36e5;
    selEl.innerHTML = `<strong>${t('Stay')}:</strong> ${duration(hours)} · <span class="muted">${t('Checking availability…')}</span>`;
    const my = ++seq;
    const res = await fetch('/api/quote', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ listing_id: listingId, start_at: startIn.value, end_at: endIn.value, guests: Number(guestsIn && guestsIn.value || 1) }) });
    if (my !== seq) return;
    if (!res.ok) { const e = await res.json(); selEl.innerHTML = `<strong>${t('Stay')}:</strong> ${duration(hours)} · <span class="err">${e.detail}</span>`; return; }
    const q = await res.json();
    selEl.innerHTML = `<strong>${t('Stay')}:</strong> ${duration(hours)} · <span class="ok">✓ ${t('Available')}</span>`;
    document.getElementById('q-lines').innerHTML = q.lines.map(l => { const one = l.label.replace(/s$/, ''); return `<div><span>${plural(l.n, one, one + 's')}</span><span>${money(l.amount_cents)}</span></div>`; }).join('');
    const xr = document.getElementById('q-extra-row'); xr.hidden = !q.extra_guest_cents; if (q.extra_guest_cents) document.getElementById('q-extra').textContent = money(q.extra_guest_cents);
    const dr = document.getElementById('q-discount-row'); dr.hidden = !q.discount_cents;
    if (q.discount_cents) document.getElementById('q-discount').textContent = '-' + money(q.discount_cents);
    document.getElementById('q-subtotal').textContent = money(q.subtotal_cents);
    document.getElementById('q-cleaning').textContent = money(q.cleaning_fee_cents); document.getElementById('q-cleaning-row').hidden = !q.cleaning_fee_cents;
    document.getElementById('q-fee').textContent = money(q.service_fee_cents); document.getElementById('q-fee-row').hidden = !q.service_fee_cents;
    document.getElementById('q-total').textContent = money(q.total_cents);
    quoteEl.hidden = false; if (btn) btn.disabled = false;
  }
  // Availability strip: mirror the picked range, and let a click set check-in / check-out days.
  const strip = document.getElementById('cal-strip');
  function paintStrip() {
    if (!strip) return;
    const a = (startIn.value || '').slice(0, 10), b = (endIn.value || '').slice(0, 10);
    strip.querySelectorAll('.cal-day').forEach(el => {
      const d = el.dataset.date;
      el.classList.toggle('sel', !!a && !!b && d >= a && d <= b);
      el.classList.toggle('sel-start', d === a); el.classList.toggle('sel-end', d === b);
    });
  }
  let pickingEnd = false, keptEndTime = null;
  if (strip) strip.addEventListener('click', e => {
    const el = e.target.closest('.cal-day'); if (!el || el.classList.contains('busy')) return;
    const d = el.dataset.date, st = (startIn.value || '').slice(11) || '10:00';
    if (!pickingEnd || d < (startIn.value || '').slice(0, 10)) { keptEndTime = (endIn.value || '').slice(11) || st; startIn.value = `${d}T${st}`; pickingEnd = true; }
    else { endIn.value = `${d}T${keptEndTime || st}`; pickingEnd = false; }
    if (endIn.value <= startIn.value) { const x = new Date(startIn.value); x.setHours(x.getHours() + Math.max(2, minH)); const p = n => String(n).padStart(2, '0'); endIn.value = `${x.getFullYear()}-${p(x.getMonth() + 1)}-${p(x.getDate())}T${p(x.getHours())}:00`; }
    update();
  });
  const _update = update; update = async function () { paintStrip(); return _update(); };

  startIn.addEventListener('change', () => { if (endIn.value <= startIn.value) { const d = new Date(startIn.value); d.setHours(d.getHours() + 2); const p = n => String(n).padStart(2, '0'); endIn.value = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:00`; } update(); });
  endIn.addEventListener('change', update);
  if (guestsIn) guestsIn.addEventListener('change', update);
  paintStrip(); update();
})();
