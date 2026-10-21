import { apiUrl } from './api-client.js';

const $ = selector => document.querySelector(selector);
const TZ = 'Europe/Riga';
const colors = {
  teal: '#4dd7c1', violet: '#b2a4ff', amber: '#ffd65d',
  coral: '#ff96aa', lime: '#b8f178', normal: '#84c9ec',
  grid: '#29404f', text: '#7895a4'
};
const state = { forecast: null, geometry: null, hoverX: null, selectedIndex: 0,
                selectedKey: null, showSelectedAnalog: true, showTodayMatch: true, todayDate: null,
                selectedDate: null, reviewMonth: null, month: null, forecastRequest: 0,
                october: null, octoberPeriod: 'all', octoberMethod: 'temperature', octoberRequest: 0,
                octoberVisible: new Set(), octoberSelectionInitialized: false,
                octoberGeometry: null, octoberHover: null };
const octoberColors = ['#ffc779', '#b2a4ff', '#ff96aa', '#84c9ec', '#b8f178'];

function localDate(ts, options = {}) {
  return new Intl.DateTimeFormat('lv-LV', { timeZone: TZ, ...options }).format(new Date(ts));
}
function temp(value, digits = 1) {
  return value == null ? '—' : `${Number(value).toFixed(digits).replace('.', ',')}°`;
}
function number(value) { return new Intl.NumberFormat('lv-LV').format(value); }
function signedTemp(value) { return `${value < 0 ? '−' : '+'}${temp(Math.abs(value), 2)}C`; }
function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, character =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]);
}
function selectedMatch() { return state.forecast?.matches[state.selectedIndex] || null; }
function dateLabel(date) {
  return localDate(`${date}T12:00:00Z`, { day: '2-digit', month: '2-digit', year: 'numeric' });
}
async function api(path) {
  const response = await fetch(apiUrl(path), { cache: 'no-store' });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}
function canvasContext(canvas) {
  const ratio = window.devicePixelRatio || 1;
  const { width, height } = canvas.getBoundingClientRect();
  canvas.width = Math.round(width * ratio);
  canvas.height = Math.round(height * ratio);
  const ctx = canvas.getContext('2d');
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  return { ctx, width, height };
}
function tickStep(value) {
  const power = Math.pow(10, Math.floor(Math.log10(Math.max(.01, value))));
  const scaled = value / power;
  return (scaled <= 1 ? 1 : scaled <= 2 ? 2 : scaled <= 5 ? 5 : 10) * power;
}
function axes(ctx, bounds, min, max, from, to, activeX) {
  const { left, right, top, bottom } = bounds;
  ctx.lineWidth = 1;
  ctx.font = '11px "DM Mono", monospace';
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  const step = tickStep((max - min) / 4);
  for (let value = Math.ceil(min / step) * step; value <= max + .001; value += step) {
    const y = bottom - (value - min) / (max - min) * (bottom - top);
    ctx.strokeStyle = colors.grid;
    ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(right, y); ctx.stroke();
    ctx.fillStyle = colors.text; ctx.fillText(`${Math.round(value)}°`, left - 12, y);
  }
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.fillStyle = colors.text;
  for (let index = 0; index < 5; index++) {
    const ts = from + (to - from) * index / 4;
    ctx.fillText(localDate(ts, { hour: '2-digit', minute: '2-digit' }),
                 left + (right - left) * index / 4, bottom + 17);
  }
  if (activeX != null) {
    ctx.strokeStyle = '#a9c4cb55'; ctx.setLineDash([4, 6]);
    ctx.beginPath(); ctx.moveTo(activeX, top); ctx.lineTo(activeX, bottom); ctx.stroke();
    ctx.setLineDash([]);
  }
}
function line(ctx, points, x, y, color, width = 2, dash = []) {
  ctx.beginPath();
  ctx.strokeStyle = color; ctx.lineWidth = width;
  ctx.lineJoin = 'round'; ctx.lineCap = 'round'; ctx.setLineDash(dash);
  let connected = false;
  for (const point of points) {
    if (point[1] == null) { connected = false; continue; }
    const px = x(point[0]), py = y(point[1]);
    if (connected) ctx.lineTo(px, py); else ctx.moveTo(px, py);
    connected = true;
  }
  ctx.stroke(); ctx.setLineDash([]);
}
function drawForecast() {
  const data = state.forecast;
  if (!data) return;
  const { ctx, width, height } = canvasContext($('#forecastChart'));
  const bounds = { left: 52, right: width - 22, top: 52, bottom: height - 48 };
  const from = data.input[0][0];
  const to = data.forecast.at(-1)[0] + 3600000;
  const pivot = data.forecast[0][0];
  const values = [
    ...data.input.map(point => point[1]), ...data.forecast.map(point => point[1]),
    ...data.actual.map(point => point[1]).filter(value => value != null),
    ...(data.normal || []).map(point => point[1]),
    ...data.lower, ...data.upper,
    ...data.matches.flatMap(match => match.continuation),
    ...(data.observedDayMatch?.values || [])
  ];
  const rawMin = Math.min(...values), rawMax = Math.max(...values);
  const pad = Math.max(1.5, (rawMax - rawMin) * .16);
  const min = rawMin - pad, max = rawMax + pad;
  const x = ts => bounds.left + (ts - from) / (to - from) * (bounds.right - bounds.left);
  const y = value => bounds.bottom - (value - min) / (max - min) * (bounds.bottom - bounds.top);
  ctx.fillStyle = '#ae9af90a';
  ctx.fillRect(x(pivot), bounds.top, bounds.right - x(pivot), bounds.bottom - bounds.top);
  axes(ctx, bounds, min, max, from, to, state.hoverX);
  ctx.font = '11px "DM Mono", monospace';
  ctx.textBaseline = 'top'; ctx.textAlign = 'left';
  ctx.fillStyle = '#76bcb4'; ctx.fillText('IEVADES 24H', bounds.left + 10, bounds.top + 12);
  ctx.fillStyle = '#b1a4e9'; ctx.fillText('PROGNOZES 24H', x(pivot) + 12, bounds.top + 12);
  ctx.strokeStyle = '#9f91d0bb'; ctx.lineWidth = 1.6; ctx.setLineDash([5, 6]);
  ctx.beginPath(); ctx.moveTo(x(pivot), bounds.top); ctx.lineTo(x(pivot), bounds.bottom); ctx.stroke();
  ctx.setLineDash([]);
  ctx.save();
  ctx.beginPath(); ctx.rect(bounds.left, bounds.top,
    bounds.right - bounds.left, bounds.bottom - bounds.top); ctx.clip();
  ctx.beginPath();
  data.forecast.forEach((point, index) =>
    index ? ctx.lineTo(x(point[0]), y(data.upper[index])) :
            ctx.moveTo(x(point[0]), y(data.upper[index])));
  for (let index = 23; index >= 0; index--)
    ctx.lineTo(x(data.forecast[index][0]), y(data.lower[index]));
  ctx.closePath(); ctx.fillStyle = '#b2a4ff24'; ctx.fill();
  ctx.shadowBlur = 10; ctx.shadowColor = '#4dd7c14b';
  line(ctx, data.input, x, y, colors.teal, 2.8); ctx.shadowBlur = 0;
  if (data.normal?.length === 24)
    line(ctx, data.normal, x, y, colors.normal, 2.4, [8, 6]);
  if (data.observedDayMatch && state.showTodayMatch)
    line(ctx, data.forecast.map((point, index) =>
      [point[0], data.observedDayMatch.values[index]]), x, y, colors.coral, 2.8, [2, 7]);
  line(ctx, data.forecast, x, y, colors.violet, 2.9);
  const chosen = selectedMatch();
  if (chosen && state.showSelectedAnalog) {
    ctx.shadowBlur = 7; ctx.shadowColor = '#ffd65d66';
    line(ctx, data.forecast.map((point, index) =>
      [point[0], chosen.continuation[index]]), x, y, colors.amber, 3.1, [3, 7]);
    ctx.shadowBlur = 0;
  }
  line(ctx, data.actual, x, y, colors.lime, 3.1);
  const last = [...data.actual].reverse().find(point => point[1] != null);
  if (last) {
    ctx.fillStyle = colors.lime; ctx.shadowBlur = 18; ctx.shadowColor = colors.lime;
    ctx.beginPath(); ctx.arc(x(last[0]), y(last[1]), 5.5, 0, Math.PI * 2); ctx.fill();
    ctx.shadowBlur = 0;
  }
  ctx.restore();
  state.geometry = { bounds, from, to, pivot, x, input: data.input };
}
function updateSelection() {
  const match = selectedMatch();
  const toggle = $('#toggleSelectedAnalog');
  toggle.hidden = !match;
  if (!match) return;
  $('#bestAnalogueLabel').textContent =
    `${state.selectedIndex === 0 ? 'Labākais' : 'Izvēlētais'} analogs · ${dateLabel(match.date)}`;
  toggle.setAttribute('aria-pressed', String(state.showSelectedAnalog));
  toggle.classList.toggle('is-off', !state.showSelectedAnalog);
  for (const button of document.querySelectorAll('[data-match-index]')) {
    const active = Number(button.dataset.matchIndex) === state.selectedIndex;
    button.classList.toggle('selected', active);
    button.setAttribute('aria-pressed', String(active));
  }
}
function renderForecast() {
  const data = state.forecast;
  $('#forecastDayLabel').textContent = `${data.targetDate} → ${data.forecastDate}`;
  $('#inputLegendLabel').textContent = state.selectedDate === state.todayDate ? 'Vakar' : `Ievade · ${dateLabel(data.targetDate)}`;
  const hasNormal = data.normal?.length === 24;
  $('#normalLegend').hidden = !hasNormal;
  $('#normalContext').hidden = !hasNormal;
  if (hasNormal) {
    $('#normalLabel').textContent = `Vēsturiskā norma · ${data.normalSampleDays} gadu izlase`;
    const firstYear = data.normalYears[0], lastYear = data.normalYears.at(-1);
    $('#normalContext').textContent = `${dateLabel(data.forecastDate)} katras stundas vidējais no ${data.normalSampleDays} iepriekšējo gadu pilnām Rīgas LU dienām (${firstYear}–${lastYear}). Šīs dienas mērījumi normā nav iekļauti.`;
  }
  const today = data.observedDayMatch, toggle = $('#toggleTodayMatch');
  toggle.hidden = !today;
  toggle.setAttribute('aria-pressed', String(state.showTodayMatch));
  toggle.classList.toggle('is-off', !state.showTodayMatch);
  if (today) {
    $('#observedMatchLabel').textContent = `${state.selectedDate === state.todayDate ? 'Šodienas' : 'Dienas'} sakritība · ${dateLabel(today.date)}`;
    toggle.title = `Pēc fakta: ${today.observedHours} izvēlētās dienas stundas, RMSE ${temp(today.rmse, 2)}C. Spied, lai pārslēgtu līkni.`;
  }
  $('#actualStatus').textContent =
    `${data.actualCount}/24 faktiskie Rīgas LU mērījumi${data.liveError ? ' · saglabātie dati' : ''}`;
  $('#matches').innerHTML = data.matches.map((match, index) =>
    `<button type="button" class="match" data-match-index="${index}" aria-pressed="false" aria-label="Rādīt ${escapeHtml(match.station)} ${escapeHtml(match.date)} analoga turpinājumu">
      <span class="match-rank">${String(index + 1).padStart(2, '0')}</span>
      <span class="match-detail">
        <span class="match-date">${dateLabel(match.date)}</span>
        <span class="match-station">${escapeHtml(match.station)} <span>${escapeHtml(match.stationId)}</span></span>
        <span class="match-meta"><span>Līknes RMSE ${temp(match.rawRmse, 2)}C</span><span>Nobīde ${signedTemp(match.anchorShift)}</span></span>
      </span>
      <span class="match-score">${match.score.toFixed(2).replace('.', ',')}<small>atbilstības kļūda</small></span>
    </button>`).join('');
  $('#candidateSources').textContent =
    `${number(data.candidates)} pilni 24+24h pāri · tikai Rīgas LU · HTDRY`;
  updateSelection();
  drawForecast();
}

function availableDates() {
  return (state.month?.days || []).filter(day => !['future', 'unavailable'].includes(day.status)).map(day => day.date);
}
function updateNavigation() {
  if (!state.selectedDate) return;
  $('#selectedDateLabel').textContent = localDate(`${state.selectedDate}T12:00:00Z`,
    { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
  const inputDate = new Date(`${state.selectedDate}T12:00:00Z`);
  inputDate.setUTCDate(inputDate.getUTCDate() - 1);
  $('#dateContext').textContent = `Ievade ${dateLabel(inputDate.toISOString().slice(0, 10))} → prognoze ${dateLabel(state.selectedDate)}`;
  const dates = availableDates(), index = dates.indexOf(state.selectedDate);
  $('#previousDay').disabled = index <= 0;
  $('#nextDay').disabled = index < 0 || index === dates.length - 1;
  $('#todayButton').classList.toggle('is-current', state.selectedDate === state.todayDate);
  $('#todayButton').setAttribute('aria-pressed', String(state.selectedDate === state.todayDate));
}
function renderMonth() {
  const data = state.month;
  if (!data) return;
  const monthDate = `${data.month}-01T12:00:00Z`;
  $('#monthTitle').textContent = localDate(monthDate, { month: 'long', year: 'numeric' });
  $('#monthSummary').innerHTML = data.completeDays
    ? `<strong>${number(data.completeDays)}</strong> pilnas dienas · MAE <strong>${temp(data.mae, 2)}C</strong> · RMSE ${temp(data.rmse, 2)}C`
    : 'Vēl nav pilnu dienu ar prognozi un faktiskajiem mērījumiem';
  const firstWeekday = (new Date(monthDate).getUTCDay() + 6) % 7;
  const blanks = Array.from({ length: firstWeekday }, () => '<span class="month-blank" aria-hidden="true"></span>').join('');
  const tiles = data.days.map(day => {
    const disabled = ['future', 'unavailable'].includes(day.status);
    const selected = day.date === state.selectedDate;
    const today = day.date === state.todayDate;
    const metric = day.status === 'complete' || day.status === 'partial'
      ? `MAE ${temp(day.mae, 1)}`
      : day.status === 'future' ? 'vēlāk' : day.status === 'unavailable' ? 'iztrūkums' : 'nav fakta';
    const detail = day.status === 'partial' ? `; ${day.actualCount}/24 faktiskās stundas` : '';
    const label = `${dateLabel(day.date)}; ievade ${dateLabel(day.inputDate)}; ${metric}${detail}`;
    return `<button type="button" class="day-tile ${day.status}${selected ? ' selected' : ''}${today ? ' today' : ''}" data-day="${day.date}" aria-label="${escapeHtml(label)}" aria-pressed="${selected}" ${disabled ? 'disabled' : ''} title="${escapeHtml(day.reason || label)}"><span class="day-number">${Number(day.date.slice(-2))}</span><span class="day-metric">${metric}</span></button>`;
  }).join('');
  $('#monthGrid').innerHTML = blanks + tiles;
  updateNavigation();
}
function nearest(points, ts) {
  let low = 0, high = points.length - 1;
  while (low < high) {
    const middle = (low + high) >> 1;
    if (points[middle][0] < ts) low = middle + 1; else high = middle;
  }
  const a = points[low], b = points[Math.max(0, low - 1)];
  return Math.abs(a[0] - ts) < Math.abs(b[0] - ts) ? a : b;
}
function showTooltip(frame, px, py, html) {
  const tip = $('#forecastTooltip');
  tip.innerHTML = html; tip.style.display = 'block';
  tip.style.left = `${Math.max(5, Math.min(frame.clientWidth - tip.offsetWidth - 5, px + 15))}px`;
  tip.style.top = `${Math.max(5, Math.min(frame.clientHeight - tip.offsetHeight - 5,
                                           py - tip.offsetHeight - 12))}px`;
}
function installInteractions() {
  const canvas = $('#forecastChart');
  canvas.addEventListener('pointermove', event => {
    const g = state.geometry, data = state.forecast;
    if (!g || !data) return;
    const rect = canvas.getBoundingClientRect(), px = event.clientX - rect.left;
    if (px < g.bounds.left || px > g.bounds.right) {
      $('#forecastTooltip').style.display = 'none'; return;
    }
    const ts = g.from + (px - g.bounds.left) / (g.bounds.right - g.bounds.left) * (g.to - g.from);
    const past = ts < g.pivot, points = past ? g.input : data.forecast;
    const point = nearest(points, ts), index = points.indexOf(point);
    const date = localDate(point[0], { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
    let html = `<strong>${date}</strong><br>${past ? 'Rīga LU mērīts' : 'Analogu prognoze'}: ${temp(point[1])}C`;
    if (!past) {
      if (data.normal?.length === 24)
        html += `<br>Vēsturiskā norma: ${temp(data.normal[index][1])}C`;
      const chosen = selectedMatch();
      if (chosen && state.showSelectedAnalog)
        html += `<br>Izvēlētais analogs: ${temp(chosen.continuation[index])}C`;
      if (data.observedDayMatch && state.showTodayMatch)
        html += `<br>Šodienas sakritība: ${temp(data.observedDayMatch.values[index])}C`;
      if (data.actual[index][1] != null)
        html += `<br>Rīga LU faktiski: ${temp(data.actual[index][1])}C`;
    }
    showTooltip(canvas.parentElement, px, event.clientY - rect.top, html);
    state.hoverX = g.x(point[0]); drawForecast();
  });
  canvas.addEventListener('pointerleave', () => {
    $('#forecastTooltip').style.display = 'none'; state.hoverX = null; drawForecast();
  });
  $('#matches').addEventListener('click', event => {
    const button = event.target.closest('button[data-match-index]');
    if (!button) return;
    state.selectedIndex = Number(button.dataset.matchIndex);
    state.selectedKey = selectedMatch()?.date;
    state.showSelectedAnalog = true;
    updateSelection(); drawForecast();
  });
  $('#toggleSelectedAnalog').addEventListener('click', () => {
    state.showSelectedAnalog = !state.showSelectedAnalog;
    updateSelection(); drawForecast();
  });
  $('#toggleTodayMatch').addEventListener('click', () => {
    state.showTodayMatch = !state.showTodayMatch;
    const button = $('#toggleTodayMatch');
    button.setAttribute('aria-pressed', String(state.showTodayMatch));
    button.classList.toggle('is-off', !state.showTodayMatch);
    drawForecast();
  });
  $('#monthGrid').addEventListener('click', event => {
    const button = event.target.closest('button[data-day]');
    if (button && !button.disabled) {
      selectDate(button.dataset.day);
      $('.date-navigator').scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });
  $('#previousDay').addEventListener('click', () => {
    const dates = availableDates(), index = dates.indexOf(state.selectedDate);
    if (index > 0) selectDate(dates[index - 1]);
  });
  $('#nextDay').addEventListener('click', () => {
    const dates = availableDates(), index = dates.indexOf(state.selectedDate);
    if (index >= 0 && index < dates.length - 1) selectDate(dates[index + 1]);
  });
  $('#todayButton').addEventListener('click', () => {
    if (state.todayDate) selectDate(state.todayDate);
  });
  new ResizeObserver(drawForecast).observe(canvas);
}
function selectDate(date) {
  if (date === state.selectedDate && state.forecast) return;
  state.selectedDate = date;
  state.selectedIndex = 0;
  state.selectedKey = null;
  state.forecast = null;
  state.geometry = null;
  $('#toggleSelectedAnalog').hidden = true;
  $('#normalLegend').hidden = true;
  $('#normalContext').hidden = true;
  const canvas = $('#forecastChart');
  canvas.getContext('2d').clearRect(0, 0, canvas.width, canvas.height);
  $('#matches').innerHTML = '<div class="loading">Aprēķina izvēlētās dienas analogus…</div>';
  updateNavigation();
  renderMonth();
  loadForecast(date);
}
async function loadForecast(date) {
  const request = ++state.forecastRequest;
  $('#actualStatus').textContent = 'Ielādē izvēlēto dienu…';
  try {
    const data = await api(`/api/forecast?date=${encodeURIComponent(date)}`);
    if (request !== state.forecastRequest || date !== state.selectedDate) return;
    state.forecast = data;
    state.selectedIndex = Math.max(0, data.matches.findIndex(match => match.date === state.selectedKey));
    state.selectedKey = data.matches[state.selectedIndex]?.date || null;
    renderForecast();
  } catch (error) {
    if (request !== state.forecastRequest) return;
    state.forecast = null;
    state.geometry = null;
    $('#toggleSelectedAnalog').hidden = true;
    $('#normalLegend').hidden = true;
    $('#normalContext').hidden = true;
    const canvas = $('#forecastChart');
    canvas.getContext('2d').clearRect(0, 0, canvas.width, canvas.height);
    $('#matches').innerHTML = `<div class="loading error">${escapeHtml(error.message)}</div>`;
    $('#actualStatus').textContent = 'Prognoze nav pieejama';
  }
}
async function loadMonth(month) {
  try {
    const data = await api(`/api/month?month=${encodeURIComponent(month)}`);
    if (month !== state.reviewMonth) return;
    state.month = data;
    renderMonth();
  } catch (error) {
    $('#monthGrid').innerHTML = `<div class="month-loading">${escapeHtml(error.message)}</div>`;
    $('#monthSummary').textContent = 'Pārskats nav pieejams';
  }
}

function octoberTargetValues(data) {
  return data.targetDays.flatMap(day => day || Array(24).fill(null));
}
function octoberMatchValues(data, match) {
  const comparison = [];
  for (let day = data.startDay; day <= data.endDay; day++) {
    const dayIndex = data.comparisonDays.indexOf(day);
    for (let hour = 0; hour < 24; hour++)
      comparison.push([(day - 1) * 24 + hour,
        dayIndex < 0 ? null : match.comparisonValues[dayIndex * 24 + hour]]);
  }
  const continuation = [[data.endDay * 24 - 1, match.comparisonValues.at(-1)]];
  match.continuationDays.forEach((day, dayIndex) => {
    for (let hour = 0; hour < 24; hour++)
      continuation.push([(data.endDay + dayIndex) * 24 + hour, day?.[hour] ?? null]);
  });
  return { comparison, continuation };
}
function drawOctober() {
  const data = state.october;
  if (!data) return;
  const { ctx, width, height } = canvasContext($('#octoberChart'));
  const bounds = { left: 53, right: width - 20, top: 39, bottom: height - 43 };
  const target = octoberTargetValues(data);
  const selected = data.matches.map((match, index) => ({ match, index }))
    .filter(({ match }) => state.octoberVisible.has(match.year));
  const series = selected.map(({ match, index }) => ({ ...octoberMatchValues(data, match), index }));
  const values = [...target.filter(value => value != null),
                  ...series.flatMap(item => [...item.comparison, ...item.continuation]
                    .map(point => point[1]).filter(value => value != null))];
  const rawMin = Math.min(...values), rawMax = Math.max(...values);
  const pad = Math.max(1.5, (rawMax - rawMin) * .1);
  const min = rawMin - pad, max = rawMax + pad;
  const x = index => bounds.left + index / (31 * 24 - 1) * (bounds.right - bounds.left);
  const y = value => bounds.bottom - (value - min) / (max - min) * (bounds.bottom - bounds.top);
  const boundary = x(data.endDay * 24 - .5);
  ctx.fillStyle = '#b2a4ff0a';
  ctx.fillRect(boundary, bounds.top, bounds.right - boundary, bounds.bottom - bounds.top);
  const step = tickStep((max - min) / 4);
  ctx.font = '11px "DM Mono", monospace';
  ctx.textBaseline = 'middle'; ctx.textAlign = 'right';
  for (let value = Math.ceil(min / step) * step; value <= max + .001; value += step) {
    const py = y(value);
    ctx.strokeStyle = colors.grid; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(bounds.left, py); ctx.lineTo(bounds.right, py); ctx.stroke();
    ctx.fillStyle = colors.text; ctx.fillText(`${value.toFixed(step < 1 ? 1 : 0)}°`, bounds.left - 10, py);
  }
  ctx.textBaseline = 'top'; ctx.textAlign = 'center';
  for (const day of [1, 5, 10, 15, 20, 25, 31]) {
    const px = x((day - 1) * 24);
    ctx.fillStyle = colors.text; ctx.fillText(`${day}. okt.`, px, bounds.bottom + 13);
  }
  ctx.strokeStyle = '#b2a4ff99'; ctx.lineWidth = 1.3; ctx.setLineDash([5, 6]);
  ctx.beginPath(); ctx.moveTo(boundary, bounds.top); ctx.lineTo(boundary, bounds.bottom); ctx.stroke();
  ctx.setLineDash([]);
  ctx.textAlign = 'left'; ctx.fillStyle = '#88c5be';
  ctx.fillText('2026 / NOVĒROTS', bounds.left + 8, bounds.top + 8);
  if (data.endDay < 31) {
    ctx.fillStyle = '#b1a4e9';
    ctx.fillText('VĒSTURISKAIS TURPINĀJUMS', Math.min(boundary + 10, bounds.right - 190), bounds.top + 8);
  }
  ctx.save();
  ctx.beginPath(); ctx.rect(bounds.left, bounds.top, bounds.right - bounds.left, bounds.bottom - bounds.top); ctx.clip();
  for (const item of series) {
    const color = octoberColors[item.index];
    line(ctx, item.comparison, x, y, color, 2.1);
    line(ctx, item.continuation, x, y, color, 2.1, [7, 6]);
  }
  ctx.shadowBlur = 8; ctx.shadowColor = '#4dd7c14b';
  line(ctx, target.map((value, index) => [index, value]), x, y, colors.teal, 2.9);
  ctx.shadowBlur = 0;
  if (state.octoberHover != null) {
    ctx.strokeStyle = '#bed0d077'; ctx.lineWidth = 1; ctx.setLineDash([3, 5]);
    ctx.beginPath(); ctx.moveTo(x(state.octoberHover), bounds.top);
    ctx.lineTo(x(state.octoberHover), bounds.bottom); ctx.stroke(); ctx.setLineDash([]);
  }
  ctx.restore();
  state.octoberGeometry = { bounds, x, target, selected };
}
function renderOctober() {
  const data = state.october;
  if (!data) return;
  const label = data.period === 'all' ? 'Viss pieejamais oktobris' : `Pēdējās ${data.period} kalendāra dienas`;
  $('#octoberWindow').textContent = `${label} · ${data.startDay}.–${data.endDay}.10.${data.targetYear} · ${data.comparisonHours} derīgas stundas`;
  $('#octoberCandidateCount').textContent = `${data.candidateYears} salīdzināmi Rīgas LU oktobri · HTDRY`;
  document.querySelectorAll('[data-october-period]').forEach(button =>
    button.setAttribute('aria-pressed', String(button.dataset.octoberPeriod === data.period)));
  document.querySelectorAll('[data-october-method]').forEach(button =>
    button.setAttribute('aria-pressed', String(button.dataset.octoberMethod === data.method)));
  const descriptions = {
    temperature: 'Rangs = 30% MAE + 40% RMSE + 30% formas RMSE. Forma salīdzina visas izvēlētā perioda stundas pēc perioda vidējās temperatūras atņemšanas.',
    profile: 'Katru pilnu dienu vērtē atsevišķi: 40% centrētas 24h līknes forma, 12% nakts 00–06 izmaiņa, 12% rīta 06–12 izmaiņa, 14% amplitūda, 14% lielākais stundas kāpums un kritums, 8% maksimuma laiks (1 h = 0,25 °C). Dienu rādītājus vidējo.',
    regime: 'Salīdzina dienu secību: 20% centrētas dienas vidējās temperatūras līkne, 40% izmaiņas starp secīgām dienām, 25% trīs secīgu dienu kopējā izmaiņa, 15% diennakts amplitūdas. Pāri iztrūkumiem neveido; nepieejamu pāreju svarus pārdala.'
  };
  $('#octoberMethodExplanation').textContent = `${descriptions[data.method]} Grafikā ir sākotnējās °C vērtības bez nobīdes. Vērtē tikai izvēlētā posma vienādās kalendāra stundas; vēsturisko turpinājumu atlasē neizmanto.`;
  const detail = match => {
    if (data.method === 'profile') return `24h forma ${temp(match.profile.shapeRmse, 2)}C · nakts ${temp(match.profile.nightChangeMae, 2)}C<br>Rīts ${temp(match.profile.morningChangeMae, 2)}C · amplitūda ${temp(match.profile.amplitudeMae, 2)}C<br>Stundas lēcieni ${temp(match.profile.jumpMae, 2)}C · maksimums ${match.profile.peakHourMae.toFixed(1).replace('.', ',')}h`;
    if (data.method === 'regime') return `Dienu ritms ${temp(match.regime.dailyChangeRmse, 2)}C · 3 dienas ${temp(match.regime.threeDayChangeRmse, 2)}C<br>Centrētie vidējie ${temp(match.regime.dailyMeanShapeRmse, 2)}C · amplitūda ${temp(match.regime.amplitudeMae, 2)}C`;
    return `MAE ${temp(match.mae, 2)}C · RMSE ${temp(match.rmse, 2)}C<br>Formas RMSE ${temp(match.shapeRmse, 2)}C`;
  };
  $('#octoberMatches').innerHTML = data.matches.length ? data.matches.map((match, index) =>
    `<button type="button" class="october-match" data-october-year="${match.year}" aria-pressed="${state.octoberVisible.has(match.year)}" style="--analog-color:${octoberColors[index]}">
      <span class="october-match-bar" aria-hidden="true"></span><span class="october-match-rank">${String(index + 1).padStart(2, '0')}</span>
      <span><strong class="october-match-year">${match.year}</strong><span class="october-match-detail">${detail(match)}<br>Turpinājumā ${match.completeContinuationDays}/${31 - data.endDay} pilnas dienas</span></span>
      <span class="october-match-score">${match.score.toFixed(2).replace('.', ',')}<small>vērtējums</small></span>
    </button>`).join('') : '<p class="loading">Šim posmam nav neviena pilna vēsturiska oktobra.</p>';
  drawOctober();
}
async function loadOctober(period, method = state.octoberMethod, resetSelection = false) {
  const request = ++state.octoberRequest;
  state.octoberPeriod = period;
  state.octoberMethod = method;
  if (resetSelection) {
    state.octoberVisible.clear();
    state.octoberSelectionInitialized = false;
    state.october = null;
    state.octoberGeometry = null;
    $('#octoberMatches').innerHTML = '<p class="loading">Pārrēķina izvēlēto periodu…</p>';
    const canvas = $('#octoberChart');
    canvas.getContext('2d').clearRect(0, 0, canvas.width, canvas.height);
  }
  document.querySelectorAll('[data-october-period]').forEach(button =>
    button.setAttribute('aria-pressed', String(button.dataset.octoberPeriod === period)));
  document.querySelectorAll('[data-october-method]').forEach(button =>
    button.setAttribute('aria-pressed', String(button.dataset.octoberMethod === method)));
  $('#octoberWindow').textContent = 'Aprēķina vēsturisko oktobru līdzību…';
  try {
    const data = await api(`/api/october-analogues?period=${encodeURIComponent(period)}&method=${encodeURIComponent(method)}`);
    if (request !== state.octoberRequest) return;
    state.october = data;
    const available = new Set(data.matches.map(match => match.year));
    state.octoberVisible = new Set([...state.octoberVisible].filter(year => available.has(year)));
    if (!state.octoberSelectionInitialized && data.matches.length)
      state.octoberVisible.add(data.matches[0].year);
    state.octoberSelectionInitialized = true;
    renderOctober();
  } catch (error) {
    if (request !== state.octoberRequest) return;
    state.october = null;
    state.octoberGeometry = null;
    $('#octoberWindow').textContent = error.message;
    $('#octoberCandidateCount').textContent = '';
    $('#octoberMatches').innerHTML = '<p class="loading error">Salīdzinājums nav pieejams.</p>';
    const canvas = $('#octoberChart');
    canvas.getContext('2d').clearRect(0, 0, canvas.width, canvas.height);
  }
}
function installOctoberInteractions() {
  document.querySelector('.october-periods').addEventListener('click', event => {
    const button = event.target.closest('[data-october-period]');
    if (button && button.dataset.octoberPeriod !== state.octoberPeriod)
      loadOctober(button.dataset.octoberPeriod, state.octoberMethod, true);
  });
  document.querySelector('.october-methods').addEventListener('click', event => {
    const button = event.target.closest('[data-october-method]');
    if (button && button.dataset.octoberMethod !== state.octoberMethod)
      loadOctober(state.octoberPeriod, button.dataset.octoberMethod, true);
  });
  $('#octoberMatches').addEventListener('click', event => {
    const button = event.target.closest('[data-october-year]');
    if (!button) return;
    const year = Number(button.dataset.octoberYear);
    if (state.octoberVisible.has(year)) state.octoberVisible.delete(year);
    else state.octoberVisible.add(year);
    button.setAttribute('aria-pressed', String(state.octoberVisible.has(year)));
    drawOctober();
  });
  const canvas = $('#octoberChart');
  canvas.addEventListener('pointermove', event => {
    const data = state.october, g = state.octoberGeometry;
    if (!data || !g) return;
    const rect = canvas.getBoundingClientRect(), px = event.clientX - rect.left;
    if (px < g.bounds.left || px > g.bounds.right) {
      $('#octoberTooltip').style.display = 'none'; return;
    }
    const index = Math.max(0, Math.min(743, Math.round((px - g.bounds.left) /
      (g.bounds.right - g.bounds.left) * 743)));
    const day = Math.floor(index / 24) + 1, hour = index % 24;
    const actual = g.target[index];
    let html = `<strong>${day}. okt. ${String(hour).padStart(2, '0')}:00</strong><br>2026: ${temp(actual)}C`;
    for (const { match } of g.selected) {
      const dayIndex = data.comparisonDays.indexOf(day);
      const value = day <= data.endDay
        ? dayIndex < 0 ? null : match.comparisonValues[dayIndex * 24 + hour]
        : match.continuationDays[day - data.endDay - 1]?.[hour];
      if (value != null)
        html += `<br>${match.year}${day > data.endDay ? ' turpinājums' : ''}: ${temp(value)}C`;
    }
    const tip = $('#octoberTooltip');
    tip.innerHTML = html; tip.style.display = 'block';
    tip.style.left = `${Math.max(5, Math.min(canvas.clientWidth - tip.offsetWidth - 5, px + 13))}px`;
    tip.style.top = `${Math.max(5, Math.min(canvas.clientHeight - tip.offsetHeight - 5, event.clientY - rect.top - tip.offsetHeight - 12))}px`;
    state.octoberHover = index;
    drawOctober();
  });
  canvas.addEventListener('pointerleave', () => {
    $('#octoberTooltip').style.display = 'none';
    state.octoberHover = null; drawOctober();
  });
  new ResizeObserver(drawOctober).observe(canvas);
}
async function initialize() {
  try {
    const status = await api('/api/status');
    state.todayDate = status.today;
    state.selectedDate = status.today;
    state.reviewMonth = status.reviewMonth;
    updateNavigation();
    await Promise.allSettled([loadForecast(status.today), loadMonth(status.reviewMonth), loadOctober('all')]);
  } catch (error) {
    $('#matches').innerHTML = `<div class="loading error">${escapeHtml(error.message)}</div>`;
    $('#actualStatus').textContent = 'Savienojums nav pieejams';
  }
}
async function refresh() {
  try {
    const status = await api('/api/status');
    const wasToday = state.selectedDate === state.todayDate;
    state.todayDate = status.today;
    if (wasToday) state.selectedDate = status.today;
    if (state.reviewMonth !== status.reviewMonth) {
      state.reviewMonth = status.reviewMonth;
      state.month = null;
    }
    updateNavigation();
    await Promise.allSettled([loadForecast(state.selectedDate), loadMonth(state.reviewMonth),
                              loadOctober(state.octoberPeriod)]);
  } catch (error) {
    $('#actualStatus').textContent = `Atjaunināšana neizdevās: ${error.message}`;
  }
}
installInteractions();
installOctoberInteractions();
initialize();
setInterval(refresh, 600000);
