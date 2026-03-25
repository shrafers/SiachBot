#!/usr/bin/env python3
"""Generate a visual HTML review tool for organizing recordings into series."""

import json

with open('data/tagged_recordings.json') as f:
    raw = json.load(f)

records = []
for r in raw:
    records.append({
        'id': r['message_id'],
        'date': r.get('date', ''),
        'year': r.get('date', '????')[:4],
        'teacher': r.get('teacher') or 'לא ידוע',
        'series': r.get('series_name') or '',
        'title': r.get('title') or r.get('filename', ''),
        'duration': r.get('duration_seconds', 0),
    })

data_json = json.dumps(records, ensure_ascii=False)

html = """<!DOCTYPE html>
<html dir="rtl" lang="he">
<head>
  <meta charset="UTF-8">
  <title>עורך סדרות שיעורים</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Segoe UI', Arial, sans-serif; background: #f0f2f5; color: #1a1a2e; height: 100vh; display: flex; flex-direction: column; overflow: hidden; }

    .header { background: #1a1a2e; color: white; padding: 12px 20px; display: flex; align-items: center; gap: 16px; flex-shrink: 0; }
    .header h1 { font-size: 17px; font-weight: 600; }
    .header .stats { font-size: 12px; color: #aaa; margin-right: auto; }

    .layout { display: flex; flex: 1; overflow: hidden; }

    /* Sidebar */
    .sidebar { width: 210px; background: white; border-left: 1px solid #e0e0e0; overflow-y: auto; flex-shrink: 0; }
    .sidebar-title { padding: 10px 14px; font-size: 11px; font-weight: 700; color: #999; border-bottom: 1px solid #f0f0f0; text-transform: uppercase; letter-spacing: 0.5px; }
    .teacher-item { padding: 9px 14px; cursor: pointer; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #f5f5f5; }
    .teacher-item:hover { background: #f5f7ff; }
    .teacher-item.active { background: #eef2ff; color: #4338ca; font-weight: 600; }
    .teacher-count { font-size: 11px; color: #bbb; background: #f5f5f5; padding: 1px 6px; border-radius: 10px; }
    .teacher-item.active .teacher-count { background: #c7d2fe; color: #4338ca; }

    /* Main */
    .main { flex: 1; overflow-y: auto; padding: 16px 20px 90px; }

    .year-section { margin-bottom: 20px; }
    .year-header { font-size: 12px; font-weight: 700; color: #666; margin-bottom: 8px; padding: 5px 10px; background: #e8ecf5; border-radius: 6px; display: flex; align-items: center; gap: 8px; }
    .year-count { font-weight: 400; color: #999; }
    .select-year-btn { font-size: 11px; color: #6366f1; cursor: pointer; padding: 2px 8px; border-radius: 4px; background: #eef2ff; border: none; font-family: inherit; margin-right: auto; }
    .select-year-btn:hover { background: #e0e7ff; }

    /* Cards */
    .card {
      background: white; border-radius: 7px; padding: 9px 12px; cursor: pointer;
      display: flex; align-items: center; gap: 10px; margin-bottom: 5px;
      border: 2px solid transparent; border-right: 4px solid #ddd;
      transition: box-shadow 0.1s;
    }
    .card:hover { box-shadow: 0 1px 6px rgba(0,0,0,0.08); }
    .card.selected { border-color: #6366f1 !important; background: #f5f3ff; }

    .card-body { flex: 1; min-width: 0; }
    .card-title { font-size: 13px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .card-meta { font-size: 11px; color: #bbb; margin-top: 1px; }

    .series-badge {
      font-size: 11px; padding: 3px 8px; border-radius: 12px; white-space: nowrap; flex-shrink: 0;
      cursor: pointer; transition: opacity 0.1s;
    }
    .series-badge:hover { opacity: 0.8; }
    .series-badge.has-series { color: white; }
    .series-badge.no-series { background: #f5f5f5; color: #ccc; border: 1px dashed #ddd; }
    .series-badge.changed { outline: 2px solid #fbbf24; }

    .card-date { font-size: 11px; color: #bbb; flex-shrink: 0; width: 50px; text-align: center; }

    /* Action bar */
    .action-bar {
      position: fixed; bottom: 0; left: 0; right: 0; z-index: 100;
      background: white; border-top: 2px solid #e0e0e0;
      padding: 10px 16px; display: flex; align-items: center; gap: 8px;
      box-shadow: 0 -2px 12px rgba(0,0,0,0.06);
    }
    .sel-info { font-size: 13px; color: #666; min-width: 100px; flex-shrink: 0; }
    .sel-info strong { color: #4338ca; }

    .input-wrap { flex: 1; position: relative; max-width: 380px; }
    .series-input { width: 100%; padding: 8px 12px; border: 2px solid #ddd; border-radius: 8px; font-size: 14px; font-family: inherit; direction: rtl; }
    .series-input:focus { outline: none; border-color: #6366f1; }

    .suggestions {
      position: absolute; bottom: 100%; right: 0; left: 0; margin-bottom: 4px;
      background: white; border: 1px solid #ddd; border-radius: 8px;
      box-shadow: 0 -4px 12px rgba(0,0,0,0.1); max-height: 220px; overflow-y: auto; z-index: 200;
    }
    .sug-item { padding: 7px 12px; cursor: pointer; font-size: 13px; display: flex; justify-content: space-between; align-items: center; }
    .sug-item:hover { background: #f5f7ff; }
    .sug-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; margin-left: 6px; }
    .sug-count { font-size: 11px; color: #bbb; }

    .btn { padding: 8px 14px; border-radius: 7px; font-size: 13px; font-weight: 600; cursor: pointer; border: none; font-family: inherit; white-space: nowrap; }
    .btn:disabled { opacity: 0.5; cursor: not-allowed; }
    .btn-primary { background: #6366f1; color: white; }
    .btn-primary:hover:not(:disabled) { background: #4f46e5; }
    .btn-ghost { background: #f3f4f6; color: #555; }
    .btn-ghost:hover { background: #e5e7eb; }
    .btn-export { background: #059669; color: white; }
    .btn-export:hover { background: #047857; }

    .empty { text-align: center; padding: 60px; color: #bbb; }
    .empty-icon { font-size: 40px; margin-bottom: 10px; }
  </style>
</head>
<body>

<div class="header">
  <h1>🎵 עורך סדרות שיעורים</h1>
  <div class="stats" id="header-stats">טוען...</div>
</div>

<div class="layout">
  <div class="sidebar">
    <div class="sidebar-title">מרצים</div>
    <div id="teacher-list"></div>
  </div>
  <div class="main" id="main"></div>
</div>

<div class="action-bar">
  <div class="sel-info">נבחרו: <strong id="sel-count">0</strong></div>
  <div class="input-wrap">
    <input type="text" class="series-input" id="series-input" placeholder="שם הסדרה (Enter לשיוך)..." autocomplete="off">
    <div class="suggestions" id="suggestions" style="display:none"></div>
  </div>
  <button class="btn btn-primary" id="assign-btn" onclick="assignSeries()" disabled>שייך ✓</button>
  <button class="btn btn-ghost" onclick="removeAssignment()">הסר סדרה</button>
  <button class="btn btn-ghost" onclick="clearSelection()">בטל בחירה</button>
  <button class="btn btn-export" onclick="exportCSV()">ייצא CSV ⬇</button>
</div>

<script>
const RECORDINGS = """ + data_json + """;

// State
let currentTeacher = null;
let selectedIds = new Set();
let assignments = {};   // id -> series string
let lastClickedId = null;

// Palette of distinct colors
const PALETTE = [
  '#6366f1','#ec4899','#f59e0b','#10b981','#3b82f6','#8b5cf6',
  '#ef4444','#06b6d4','#84cc16','#f97316','#14b8a6','#a855f7',
  '#22c55e','#eab308','#0ea5e9','#d946ef','#dc2626','#2563eb',
  '#7c3aed','#0891b2',
];
const colorCache = {};
let colorIdx = 0;
function colorFor(series) {
  if (!series) return null;
  if (!colorCache[series]) colorCache[series] = PALETTE[colorIdx++ % PALETTE.length];
  return colorCache[series];
}

// Init assignments from current data
RECORDINGS.forEach(r => { assignments[r.id] = r.series || ''; });

// Pre-assign colors to existing series so they stay stable
const existingSeries = [...new Set(RECORDINGS.map(r => r.series).filter(Boolean))].sort();
existingSeries.forEach(s => colorFor(s));

// Build sorted teacher list (use index-based refs to avoid spaces/quotes in IDs)
const teacherCounts = {};
RECORDINGS.forEach(r => { teacherCounts[r.teacher] = (teacherCounts[r.teacher] || 0) + 1; });
const teachersSorted = Object.entries(teacherCounts).sort((a,b) => b[1]-a[1]);

function esc(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── Render sidebar ──────────────────────────────────────
function renderSidebar() {
  document.getElementById('teacher-list').innerHTML = teachersSorted.map(([name, count], idx) =>
    `<div class="teacher-item" onclick="selectTeacher(${idx})" data-idx="${idx}">
      <span>${esc(name)}</span>
      <span class="teacher-count">${count}</span>
    </div>`
  ).join('');
}

// ── Select teacher ───────────────────────────────────────
function selectTeacher(idx) {
  // Deactivate previous
  const prevEl = document.querySelector('.teacher-item.active');
  if (prevEl) prevEl.classList.remove('active');
  // Activate new
  const el = document.querySelector(`.teacher-item[data-idx="${idx}"]`);
  if (el) el.classList.add('active');
  currentTeacher = teachersSorted[idx][0];
  selectedIds.clear();
  renderCards();
  updateBar();
}

// ── Render cards ─────────────────────────────────────────
function renderCards() {
  const main = document.getElementById('main');
  if (!currentTeacher) { main.innerHTML = '<div class="empty"><div class="empty-icon">👈</div>בחר מרצה</div>'; return; }

  const recs = RECORDINGS.filter(r => r.teacher === currentTeacher)
                          .sort((a,b) => a.date.localeCompare(b.date));

  // Group by year
  const byYear = {};
  recs.forEach(r => { (byYear[r.year] = byYear[r.year]||[]).push(r); });

  let html = '';
  Object.keys(byYear).sort().forEach(year => {
    const yrecs = byYear[year];
    html += `<div class="year-section">
      <div class="year-header">
        📅 ${year} <span class="year-count">${yrecs.length} שיעורים</span>
        <button class="select-year-btn" onclick="selectYear(event,'${year}')">בחר שנה</button>
      </div>
      <div>`;
    yrecs.forEach(r => html += cardHtml(r));
    html += '</div></div>';
  });

  main.innerHTML = html;
}

function cardHtml(r) {
  const series = assignments[r.id];
  const color = colorFor(series);
  const sel = selectedIds.has(r.id);
  const changed = series !== (r.series||'');
  const dur = r.duration ? Math.round(r.duration/60) + ' דק׳' : '';
  const borderColor = color || '#ddd';
  const mmdd = r.date ? r.date.slice(5) : '';
  return `<div class="card${sel?' selected':''}" id="card-${r.id}"
    onclick="cardClick(event,${r.id})" style="border-right-color:${borderColor}">
    <div class="card-body">
      <div class="card-title">${esc(r.title)}</div>
      <div class="card-meta">${dur}</div>
    </div>
    <div class="series-badge ${series?'has-series':'no-series'}${changed?' changed':''}"
      style="${color?'background:'+color+';':''}"
      onclick="badgeClick(event,${r.id})">${esc(series||'ללא סדרה')}</div>
    <div class="card-date">${mmdd}</div>
  </div>`;
}

function refreshCard(id) {
  const el = document.getElementById('card-'+id);
  if (!el) return;
  const r = RECORDINGS.find(x => x.id === id);
  el.outerHTML = cardHtml(r);
  if (selectedIds.has(id)) {
    const newEl = document.getElementById('card-'+id);
    if (newEl) newEl.classList.add('selected');
  }
}

// ── Card interactions ────────────────────────────────────
function cardClick(e, id) {
  if (e.shiftKey && lastClickedId !== null) {
    const recs = RECORDINGS.filter(r => r.teacher === currentTeacher)
                            .sort((a,b) => a.date.localeCompare(b.date));
    const ids = recs.map(r => r.id);
    const i1 = ids.indexOf(lastClickedId), i2 = ids.indexOf(id);
    const [lo, hi] = i1 < i2 ? [i1,i2] : [i2,i1];
    ids.slice(lo, hi+1).forEach(rid => selectedIds.add(rid));
    // re-render selected state
    ids.slice(lo, hi+1).forEach(rid => {
      const el = document.getElementById('card-'+rid);
      if (el) el.classList.add('selected');
    });
  } else {
    const el = document.getElementById('card-'+id);
    if (selectedIds.has(id)) { selectedIds.delete(id); el && el.classList.remove('selected'); }
    else { selectedIds.add(id); el && el.classList.add('selected'); }
    lastClickedId = id;
  }
  updateBar();
}

function badgeClick(e, id) {
  e.stopPropagation();
  selectedIds.add(id);
  const el = document.getElementById('card-'+id);
  if (el) el.classList.add('selected');
  const s = assignments[id];
  if (s) document.getElementById('series-input').value = s;
  updateBar();
  document.getElementById('series-input').focus();
  showSuggestions();
}

function selectYear(e, year) {
  e.stopPropagation();
  RECORDINGS.filter(r => r.teacher === currentTeacher && r.year === year)
            .forEach(r => { selectedIds.add(r.id); const el=document.getElementById('card-'+r.id); if(el) el.classList.add('selected'); });
  updateBar();
}

// ── Assignment ───────────────────────────────────────────
function assignSeries() {
  const series = document.getElementById('series-input').value.trim();
  if (!selectedIds.size) return;
  selectedIds.forEach(id => { assignments[id] = series; });
  const ids = [...selectedIds];
  clearSelection();
  ids.forEach(id => refreshCard(id));
  updateHeaderStats();
  hideSuggestions();
}

function removeAssignment() {
  selectedIds.forEach(id => { assignments[id] = ''; });
  const ids = [...selectedIds];
  clearSelection();
  ids.forEach(id => refreshCard(id));
  updateHeaderStats();
}

function clearSelection() {
  selectedIds.forEach(id => { const el=document.getElementById('card-'+id); if(el) el.classList.remove('selected'); });
  selectedIds.clear();
  updateBar();
}

function updateBar() {
  document.getElementById('sel-count').textContent = selectedIds.size;
  document.getElementById('assign-btn').disabled = selectedIds.size === 0;
}

function updateHeaderStats() {
  const changed = RECORDINGS.filter(r => assignments[r.id] !== (r.series||'')).length;
  document.getElementById('header-stats').textContent =
    `${RECORDINGS.length} שיעורים | ${changed} שינויים לא שמורים`;
}

// ── Suggestions ──────────────────────────────────────────
function getSeriesCounts() {
  const counts = {};
  Object.values(assignments).forEach(s => { if(s) counts[s]=(counts[s]||0)+1; });
  return counts;
}

function showSuggestions() {
  const val = document.getElementById('series-input').value.trim();
  const counts = getSeriesCounts();
  let entries = Object.entries(counts).sort((a,b) => b[1]-a[1]);
  if (val) entries = entries.filter(([s]) => s.includes(val));
  entries = entries.slice(0, 20);

  if (!entries.length) { hideSuggestions(); return; }

  document.getElementById('suggestions').innerHTML = entries.map(([s, c]) => {
    const color = colorFor(s);
    return `<div class="sug-item" onclick="selectSuggestion(${JSON.stringify(s)})">
      <div style="display:flex;align-items:center;gap:6px">
        <div class="sug-dot" style="background:${color||'#ddd'}"></div>
        <span>${esc(s)}</span>
      </div>
      <span class="sug-count">${c}</span>
    </div>`;
  }).join('');
  document.getElementById('suggestions').style.display = 'block';
}

function hideSuggestions() {
  document.getElementById('suggestions').style.display = 'none';
}

function selectSuggestion(series) {
  document.getElementById('series-input').value = series;
  hideSuggestions();
  assignSeries();
}

const input = document.getElementById('series-input');
input.addEventListener('input', showSuggestions);
input.addEventListener('focus', showSuggestions);
input.addEventListener('keydown', e => {
  if (e.key === 'Enter') { assignSeries(); }
  if (e.key === 'Escape') { hideSuggestions(); clearSelection(); }
});
document.addEventListener('click', e => { if (!e.target.closest('.input-wrap')) hideSuggestions(); });

// ── Export ───────────────────────────────────────────────
function exportCSV() {
  const rows = [['message_id','teacher','date','year','title','old_series','new_series']];
  RECORDINGS.forEach(r => {
    rows.push([r.id, r.teacher, r.date, r.year, r.title||'', r.series||'', assignments[r.id]||'']);
  });
  const csv = rows.map(row =>
    row.map(v => '"' + String(v).replace(/"/g,'""') + '"').join(',')
  ).join('\\n');
  const a = document.createElement('a');
  a.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csv);
  a.download = 'series_assignments.csv';
  a.click();
}

// ── Boot ─────────────────────────────────────────────────
renderSidebar();
updateHeaderStats();
</script>
</body>
</html>"""

with open('review.html', 'w', encoding='utf-8') as f:
    f.write(html)

print(f"✅ Generated review.html  ({len(records)} recordings, {len(set(r['teacher'] for r in records))} teachers)")
