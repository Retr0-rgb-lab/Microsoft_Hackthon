import {canAnalyze, nextMoment, unavailableReason} from './coach-moments.js';
import {setupLanguage, translate} from './coach-i18n.js';
const getLanguage = setupLanguage();
const $ = s => document.querySelector(s);
const leagueRoot = new URLSearchParams(location.search).get('dataset') === 'validated' ? 'data/league-validated' : 'data/league';
let preview, report, selected, token = 0;
let agentResult = null, agentDocument = null, agentsBusy = false, analysisBusy = false;
let rollout = null, simIndex = null, animation = null, simToken = 0;
// Decision-analysis contract state (contracts/decision-analysis/README.md §3).
let analysisCatalog = null, decisionIndex = null, decisionIndexMatch = null;
function stopAnimation() { if (animation !== null) cancelAnimationFrame(animation); animation = null; }
function clearSimulation() { stopAnimation(); simToken++; rollout = null; simIndex = null; for (const id of ['scenario','play-sim','reset-sim','sim-time']) $('#'+id).disabled = true; $('#simulate').disabled = true; $('#sim-status').textContent = 'No counterfactual loaded. Actual replay and hypothetical motion are separate.'; }
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const frame = () => preview?.frames[Number($('#time').value)];
function clearReport() { agentResult = null; agentDocument = null; $('#run-agents').disabled = true; $('#agent-status').textContent = 'No model agents have run for this snapshot.'; $('#agent-answer').textContent = ''; $('#agent-caveats').replaceChildren(); $('#agent-trace').textContent = ''; clearSimulation(); report = null; selected = null; token++; $('#options').replaceChildren(); $('#detail').textContent = ''; $('#explanation').textContent = ''; $('#export').disabled = true; }
function draw() {
  const source = frame(); if (!source) return;
  $('#analyze').disabled = analysisBusy || !canAnalyze(source);
  $('#availability').textContent = canAnalyze(source) ? 'Ball controlled: pass analysis is available.' : unavailableReason(source);
  $('#prev-moment').disabled = nextMoment(preview.frames, Number($('#time').value), -1) < 0;
  $('#next-moment').disabled = nextMoment(preview.frames, Number($('#time').value), 1) < 0;
  const scenario = rollout?.scenarios.find(s => s.id === $('#scenario').value);
  const hypothesis = simIndex === null ? null : scenario?.frames[simIndex];
  const f = hypothesis ? {...source, players:hypothesis.players, ball:hypothesis.ball} : source;
  let markup = '<rect x="0" y="0" width="105" height="68" fill="none" stroke="#b5d2c4" stroke-width=".3"/><path d="M52.5 0V68M0 14H16.5V54H0M105 14H88.5V54H105" fill="none" stroke="#b5d2c4" stroke-width=".3"/><circle cx="52.5" cy="34" r="9.15" fill="none" stroke="#b5d2c4" stroke-width=".3"/>';
  if (report) for (const c of report.candidates) markup += `<path d="M${c.start.join(' ')} L${c.target.join(' ')}" fill="none" stroke="${c.action_id === selected ? '#f9ef8e' : '#79ad9c'}" stroke-width="${c.action_id === selected ? .8 : .3}" ${c.feasible_by_rules ? '' : 'stroke-dasharray="1 1"'}/><circle cx="${c.target[0]}" cy="${c.target[1]}" r=".8" fill="none" stroke="#e7e0ab" stroke-width=".3"/>`;
  const teams = new Map(preview.metadata.players.map(p => [p.player_id, p.team_id]));
  for (const p of f.players) markup += `<circle cx="${p[1]}" cy="${p[2]}" r="1.4" fill="${teams.get(p[0]) === 'HOME' ? '#72b8ff' : '#f2a66d'}" stroke="${p[0] === f.ball_owner_id ? '#fff' : '#20323d'}" stroke-width=".5"/><text x="${p[1]}" y="${p[2]-2.1}" text-anchor="middle" fill="white" font-size="2">${esc(p[0])}</text>`;
  markup += `<circle cx="${f.ball[0]}" cy="${f.ball[1]}" r=".65" fill="white"/>`;
  $('#pitch').innerHTML = markup;
  $('#clock').textContent = `${(f.t_ms/1000).toFixed(1)} s · period ${f.period}`;
  $('#snapshot').textContent = hypothesis ? `HYPOTHESIS · +${hypothesis.elapsed_s.toFixed(2)} s · ${scenario.id} · ${scenario.outcome}. Not actual match footage.` : `Owner ${f.ball_owner_id || 'unknown'} · ${f.phase} · ${preview.match_id}. Only this snapshot is submitted for analysis.`;
}
function select(id) {
  token++; agentResult = null; agentDocument = null; $('#agent-answer').textContent = ''; $('#agent-trace').textContent = ''; $('#agent-caveats').replaceChildren(); $('#agent-status').textContent = 'No model agents have run for this selected route.';
  clearSimulation(); selected = id;
  const c = report.candidates.find(c => c.action_id === id);
  $('#detail').textContent = `Pass to ${c.receiver_id}\nDefender arrival margin: ${c.evidence[0].value} s (negative means the defender may arrive before the ball).\nOffside at release: ${c.evidence[2].value}.\nThe ranking is a decision aid. The model's spatial values are uncalibrated and are deliberately not shown as numbers: they are not success or goal probabilities.`;
  for (const row of $('#options').rows) row.classList.toggle('selected', row.dataset.id === id);
  $('#simulate').disabled = !c.feasible_by_rules;
  $('#run-agents').disabled = agentsBusy;
  draw();
}
async function load() {
  clearReport(); preview = null; decisionIndex = null; decisionIndexMatch = null; $('#analyze').disabled = true; $('#pitch').replaceChildren(); $('#status').textContent = 'Loading…';
  const request = token;
  try {
    const r = await fetch($('#match').value === 'realism-sample' ? 'data/realism-sample/preview-60s.json' : `${leagueRoot}/matches/${encodeURIComponent($('#match').value)}/preview-60s.json`);
    if (!r.ok) throw Error('Preview unavailable');
    const value = await r.json(); if (request !== token) return;
    preview = value; $('#time').max = preview.frames.length-1;
    const i = preview.frames.findIndex(f => f.in_play && f.ball_owner_id);
    $('#time').value = Math.max(0, i); $('#status').textContent = 'Choose a moment, then analyze.'; draw();
  } catch (e) { if (request === token) $('#status').textContent = e.message; }
  finally { if (request === token) $('#analyze').disabled = analysisBusy || !canAnalyze(frame()); }
}
$('#time').oninput = () => { clearReport(); $('#status').textContent = 'Snapshot changed. Analyze again.'; draw(); };
$('#match').onchange = load;
$('#mode').onchange = () => { clearReport(); $('#status').textContent = 'Explanation mode changed. Analyze again.'; draw(); };
$('#analyze').onclick = async () => {
  if (!preview || analysisBusy) return;
  if (!canAnalyze(frame())) { $('#status').textContent = unavailableReason(frame()); return; }
  analysisBusy = true;
  clearReport(); draw(); const request = token; $('#analyze').disabled = true; $('#status').textContent = 'Evaluating routes and interception margins…';
  try {
    const r = await fetch('/api/decision', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({frame:frame(),metadata:{players:preview.metadata.players},mode:$('#mode').value})});
    const value = await r.json(); if (!r.ok) throw Error(value.error || 'Analysis failed'); if (request !== token) return;
    report = value; $('#status').textContent = value.status === 'ready' ? 'Computed · best among evaluated ground passes only' : value.reason;
    $('#explanation').textContent = value.status === 'ready' ? value.review.text : '';
    $('#options').innerHTML = value.candidates.map((c,i) => `<tr tabindex="0" data-id="${esc(c.action_id)}"><td>${esc(c.receiver_id)}</td><td>${c.feasible_by_rules ? 'Eligible' : 'Offside'}</td><td>${c.ball_travel_s.toFixed(1)} s</td><td>${c.evidence[0].value} s</td><td>${esc(c.evidence[0].player_id)}</td></tr>`).join('');
    for (const row of $('#options').rows) { row.onclick = () => select(row.dataset.id); row.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); select(row.dataset.id); } }; }
    $('#export').disabled = false;
    if (value.recommended_action_id) select(value.recommended_action_id); else draw();
  } catch(e) { if (request === token) $('#status').textContent = e.message; }
  finally { analysisBusy = false; $('#analyze').disabled = !canAnalyze(frame()); }
};
$('#export').onclick = () => {
  if (!report) return;
  const blob = new Blob([JSON.stringify({match_id:preview.match_id,frame:frame(),analysis:report,rollout,decision_analysis:{document:agentDocument,response:agentResult}},null,2)],{type:'application/json'});
  const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = `${preview.match_id}-${report.t_ms}-decision.json`; a.click(); setTimeout(() => URL.revokeObjectURL(url),1000);
};
// Decision-analysis contract. Call order follows contracts/decision-analysis/README.md §3:
// catalog -> index -> context -> analyze -> agents. The request sent to the server is the
// canonical request issued by the context route; only question, mode and language may change.
async function contractGet(path) {
  const r = await fetch(path, {cache:'no-store'});
  const value = await r.json();
  if (!r.ok) throw Error(value.error || 'Decision-analysis service unavailable');
  return value;
}
async function contractPost(path, body) {
  const r = await fetch(path, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const value = await r.json();
  if (!r.ok) throw Error(value.error || 'Decision-analysis service unavailable');
  return value;
}
async function loadCatalog() {
  if (!analysisCatalog) analysisCatalog = await contractGet('/api/decision-analysis/catalog');
  return analysisCatalog;
}
async function loadDecisionIndex(matchId) {
  if (!decisionIndex || decisionIndexMatch !== matchId) {
    decisionIndex = await contractGet('/api/decision-analysis/index?match_id='+encodeURIComponent(matchId));
    decisionIndexMatch = matchId;
  }
  return decisionIndex;
}
// The exact moment wins; otherwise the nearest registered decision at or before the previewed frame.
function pickDecisionRecord(records, tMs) {
  const exact = records.find(r => r.t_ms === tMs);
  if (exact) return exact;
  const usable = records.filter(r => r.analyzable !== false);
  const pool = usable.length ? usable : records;
  let best = null;
  for (const r of pool) if (r.t_ms <= tMs && (!best || r.t_ms > best.t_ms)) best = r;
  return best;
}
async function decisionContext() {
  const source = frame();
  const matchId = preview?.match_id;
  if (!source || !matchId) throw Error(translate('No tracking snapshot loaded.', getLanguage()));
  const catalog = await loadCatalog();
  if (!Array.isArray(catalog.matches) || !catalog.matches.some(m => m.match_id === matchId))
    throw Error(translate('This match is not covered by the decision-analysis catalog.', getLanguage()));
  const index = await loadDecisionIndex(matchId);
  const record = pickDecisionRecord(index.records || [], source.t_ms);
  if (!record) throw Error(translate('No registered decision covers this moment.', getLanguage()));
  const context = await contractGet('/api/decision-analysis/context?match_id='+encodeURIComponent(matchId)+'&decision_id='+encodeURIComponent(record.decision_id));
  return {record, context, source, matchId};
}

try {
  const r = await fetch(`${leagueRoot}/fixtures.jsonl`); if (!r.ok) throw Error('League unavailable');
  const fixtures = (await r.text()).trim().split('\n').filter(Boolean).map(line => JSON.parse(line));
  $('#match').innerHTML = fixtures.map(f => `<option value="${esc(f.match_id)}">${esc(f.match_id)}</option>`).join('');
  $('#match').insertAdjacentHTML('afterbegin', '<option value="realism-sample">Calibrated simulation · real event reference</option>');
  if (new URLSearchParams(location.search).has('realism')) $('#match').value = 'realism-sample';
  await load();
} catch(e) { $('#status').textContent = e.message; $('#analyze').disabled = true; }

function chooseScenario() {
  stopAnimation();
  const s = rollout.scenarios.find(s => s.id === $('#scenario').value);
  simIndex = 0; $('#sim-time').max = s.frames.length-1; $('#sim-time').value = 0;
  $('#sim-status').textContent = `HYPOTHESIS: ${s.id} · reaction ${s.reaction_s}s · pass offset ${s.lateral_error_m}m · ${s.outcome}${s.controller_id ? ' by '+s.controller_id : ''}. ${rollout.summary} These cases are not probability estimates.`;
  draw();
}
$('#simulate').onclick = async () => {
  if (!report || !selected) return;
  stopAnimation(); const request = ++simToken; const snapshotToken = token;
  $('#simulate').disabled = true; $('#sim-status').textContent = 'Simulating four bounded hypotheses…';
  try {
    const r = await fetch('/api/rollout',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({frame:frame(),metadata:{players:preview.metadata.players},action_id:selected})});
    const value = await r.json(); if (!r.ok) throw Error(value.error || 'Simulation failed');
    if (request !== simToken || snapshotToken !== token) return;
    rollout = value;
    $('#scenario').innerHTML = value.scenarios.map(s => `<option value="${esc(s.id)}">${esc(s.id)} · ${esc(s.outcome)}</option>`).join('');
    for (const id of ['scenario','play-sim','reset-sim','sim-time']) $('#'+id).disabled = false;
    chooseScenario();
  } catch(e) { if (request === simToken) $('#sim-status').textContent = e.message; }
  finally { if (request === simToken && report) $('#simulate').disabled = false; }
};
$('#scenario').onchange = chooseScenario;
$('#sim-time').oninput = () => { stopAnimation(); simIndex = Number($('#sim-time').value); draw(); };
$('#reset-sim').onclick = () => { stopAnimation(); simIndex = null; $('#sim-status').textContent = 'Showing original snapshot. Hypotheses remain available to replay.'; draw(); };
$('#play-sim').onclick = () => {
  if (!rollout) return;
  chooseScenario(); const scenario = rollout.scenarios.find(s => s.id === $('#scenario').value);
  const started = performance.now();
  function tick(now) {
    simIndex = Math.min(scenario.frames.length-1, Math.floor((now-started)/50));
    $('#sim-time').value = simIndex; draw();
    animation = simIndex < scenario.frames.length-1 ? requestAnimationFrame(tick) : null;
  }
  animation = requestAnimationFrame(tick);
};

function renderAgentContract(value, doc, record, source) {
  const cited = Array.isArray(value.explanation?.cited_evidence_ids) ? value.explanation.cited_evidence_ids : [];
  const evidence = Array.isArray(value.evidence) ? value.evidence : [];
  const limitations = Array.isArray(value.limitations) ? value.limitations : [];
  const trace = Array.isArray(value.agent_trace) ? value.agent_trace : [];
  const analysedAt = doc.snapshot?.t_ms ?? record.t_ms;
  const parts = ['Status: '+value.status,
    'candidate_set_id: '+value.candidate_set_id,
    'data_version: '+value.data_version,
    'cited evidence: '+cited.length+'/'+evidence.length,
    'decision_id: '+record.decision_id,
    'snapshot_id: '+value.snapshot_id];
  if (analysedAt !== source.t_ms) parts.push('nearest registered decision, '+((source.t_ms-analysedAt)/1000).toFixed(1)+' s before the previewed frame');
  $('#agent-status').textContent = parts.join(' · ');
  const noExplanation = value.status === 'model_unavailable'
    ? 'The language agent is not connected, so no explanation was produced. The computed comparison and its limitations are unchanged.'
    : 'The agent run returned no explanation text. The computed comparison and its limitations are unchanged.';
  $('#agent-answer').textContent = value.explanation?.text
    ? translate(value.explanation.text, getLanguage())
    : translate(noExplanation, getLanguage());
  const items = cited.map(id => 'cited evidence: '+id).concat(limitations.map(t => translate(t, getLanguage())));
  $('#agent-caveats').replaceChildren(...items.map(text => { const li = document.createElement('li'); li.textContent = text; return li; }));
  $('#agent-trace').textContent = JSON.stringify({candidate_set_id:value.candidate_set_id, data_version:value.data_version, status:value.status, agent_trace:trace, evidence:evidence}, null, 2);
}
$('#run-agents').onclick = async () => {
  if (!report || agentsBusy) return;
  const question = $('#agent-question').value.trim();
  if (!question) { $('#agent-status').textContent = translate('Enter a question first.', getLanguage()); return; }
  const request = token; const analysis = report;
  agentsBusy = true; $('#run-agents').disabled = true;
  $('#agent-status').textContent = translate('Running the decision-analysis contract: catalog, index, context, analyze, agents. The trace appears when the bounded review finishes.', getLanguage());
  $('#agent-answer').textContent = ''; $('#agent-caveats').replaceChildren(); $('#agent-trace').textContent = '';
  try {
    const {record, context, source} = await decisionContext();
    // The canonical request comes from the context route; only question, mode and language change.
    const bound = {...context.request, question, mode: $('#mode').value, language: getLanguage()};
    const doc = await contractPost('/api/decision-analysis/analyze', bound);
    const value = await contractPost('/api/decision-analysis/agents', {request: bound, candidate_set_id: doc.candidate_set_id});
    if (request !== token || report !== analysis) return;
    agentResult = value; agentDocument = doc;
    renderAgentContract(value, doc, record, source);
  } catch(e) { if (request === token) $('#agent-status').textContent = translate(e.message, getLanguage()); }
  finally { agentsBusy = false; $('#run-agents').disabled = !report; }
};

window.addEventListener('nextplay-language', () => {
  const input = $('#agent-question');
  const defaults = ['Why not pass along this route? Explain the risk and alternatives.','为什么不沿这条路线传球？请解释风险和其他选择。'];
  if (defaults.includes(input.value)) input.value = getLanguage() === 'zh' ? defaults[1] : defaults[0];
  // Discard in-flight prose in the old language, without changing numeric analysis.
  token++; agentResult = null; agentDocument = null;
  $('#agent-answer').textContent = ''; $('#agent-caveats').replaceChildren(); $('#agent-trace').textContent = '';
  $('#agent-status').textContent = 'No model agents have run for this snapshot.';
});
if (getLanguage() === 'zh') $('#agent-question').value = '为什么不沿这条路线传球？请解释风险和其他选择。';

for (const [id, direction] of [['prev-moment', -1], ['next-moment', 1]]) {
  $('#'+id).onclick = () => {
    if (!preview) return;
    const i = nextMoment(preview.frames, Number($('#time').value), direction);
    if (i < 0) return;
    $('#time').value = i; clearReport();
    $('#status').textContent = 'Controlled moment selected. Analyze to compare passes.'; draw();
  };
}
