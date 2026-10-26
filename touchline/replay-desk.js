import { formatClock } from './core.js?v=2.2.0';

const esc = value => String(value ?? "").replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
const $ = selector => document.querySelector(selector);

// A decision stays on screen for eight seconds of match time, which is how long
// the moment it describes is still recognisable on the pitch.
const DECISION_WINDOW_MS = 8000;
// Paused anywhere else, the closest registered decision still describes the
// situation reasonably well, as long as the panel says how far back it is.
const PAUSED_LOOKBACK_MS = 30000;
// One comparison costs about 0.9 s of server work. At 1x the next decision is
// 2.2 s away, so the read has to start before the playhead arrives.
const PREFETCH_AHEAD = 3;
const CACHE_LIMIT = 24;

export function createReplayDesk(getState) {
  const desk = $("#replay-desk");
  const analysis = $("#ask-analysis");
  const status = $("#ask-status");
  const form = $("#ask-form");
  const answer = $("#ask-answer");
  const narration = $("#ask-narration");
  const measures = $("#ask-measures");
  const clockLabel = $("#ask-clock");
  const followLabel = $("#ask-follow");
  let matchId = "";
  let index = null;
  let shownId = "";
  let bundle = null;
  let doc = null;
  let token = 0;
  let inFlight = false;
  let mode = "fan";
  let picked = "";
  const cache = new Map();

  function collapse(buttonId, bodyId, className) {
    const button = $(buttonId);
    const body = $(bodyId);
    button.addEventListener("click", () => {
      const open = button.getAttribute("aria-expanded") === "true";
      button.setAttribute("aria-expanded", String(!open));
      button.textContent = open ? "Show" : "Hide";
      body.hidden = open;
      desk.classList.toggle(className, open);
    });
  }
  collapse("#collapse-data", "#desk-data-body", "is-data-collapsed");
  collapse("#collapse-ask", "#desk-ask-body", "is-ask-collapsed");

  function showBoard(mode) {
    $("#player-board").hidden = mode !== "player";
    $("#team-board").hidden = mode === "player";
    for (const button of document.querySelectorAll("[data-board]")) {
      button.setAttribute("aria-pressed", String(button.dataset.board === mode));
    }
    if (mode !== "player") {
      const { metadata } = getState();
      const team = metadata?.teams?.find(item => item.team_id === (mode === "home" ? "HOME" : "AWAY"));
      $("#team-board-label").textContent = team ? `${team.name} · totals follow the replay clock.` : "Team totals follow the replay clock.";
    }
  }
  for (const button of document.querySelectorAll("[data-board]")) {
    button.addEventListener("click", () => showBoard(button.dataset.board));
  }
  window.addEventListener("touchline-player", () => showBoard("player"));

  async function loadIndex(id) {
    const response = await fetch(`/api/decision-analysis/index?match_id=${encodeURIComponent(id)}`, { cache: "no-store" });
    const value = await response.json();
    if (!response.ok) throw new Error(value.error || "Decision index unavailable.");
    return value;
  }

  function nearest(time, window = DECISION_WINDOW_MS) {
    if (!index) return null;
    let found = null;
    for (const row of index.records) {
      if (row.t_ms <= time && (time - row.t_ms) <= window) found = row;
      else if (row.t_ms > time) break;
    }
    return found;
  }

  function aheadOf(time, count) {
    if (!index) return [];
    return index.records.filter(row => row.t_ms > time).slice(0, count);
  }

  async function read(row) {
    if (cache.has(row.decision_id)) return cache.get(row.decision_id);
    const context = await fetch(`/api/decision-analysis/context?match_id=${encodeURIComponent(matchId)}&decision_id=${encodeURIComponent(row.decision_id)}`, { cache: "no-store" });
    const next = await context.json();
    if (!context.ok) throw new Error(next.error || "Decision context unavailable.");
    const analyzed = await fetch("/api/decision-analysis/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(next.request),
    });
    const value = await analyzed.json();
    if (!analyzed.ok) throw new Error(value.error || "Analysis unavailable.");
    const entry = { bundle: next, doc: value };
    cache.set(row.decision_id, entry);
    if (cache.size > CACHE_LIMIT) cache.delete(cache.keys().next().value);
    return entry;
  }

  // Prefetch only when nothing else is in flight, so a slow read never stacks up
  // behind the playhead. At high speed this simply samples fewer decisions.
  function warm(time) {
    if (inFlight || !index) return;
    const next = aheadOf(time, PREFETCH_AHEAD).find(row => !cache.has(row.decision_id));
    if (!next) return;
    inFlight = true;
    read(next).catch(() => {}).finally(() => { inFlight = false; });
  }

  function fact(value, digits = 1) {
    return value == null || !Number.isFinite(value) ? "—" : value.toFixed(digits);
  }

  function renderMeasures(actorId) {
    const { frame, metadata } = getState();
    const player = metadata?.players?.find(item => item.player_id === actorId);
    if (!player || !frame) { measures.innerHTML = ""; return; }
    const onPitch = frame.players.find(item => item[0] === actorId);
    const speed = onPitch ? Math.hypot(onPitch[3], onPitch[4]) * 3.6 : null;
    const toBall = onPitch && frame.ball ? Math.hypot(onPitch[1] - frame.ball[0], onPitch[2] - frame.ball[1]) : null;
    let nearest = null;
    if (onPitch) {
      for (const other of frame.players) {
        if (other[0][0] === actorId[0]) continue;
        const distance = Math.hypot(other[1] - onPitch[1], other[2] - onPitch[2]);
        if (nearest == null || distance < nearest) nearest = distance;
      }
    }
    const team = metadata.teams.find(item => item.team_id === player.team_id);
    measures.innerHTML =
      `<div><span>On the ball</span><strong>${esc(team?.short_name || team?.name || "")} #${esc(player.jersey_number)}</strong></div>` +
      `<div><span>Instant speed</span><strong>${fact(speed)} <small>km/h</small></strong></div>` +
      `<div><span>Distance to ball</span><strong>${fact(toBall)} <small>m</small></strong></div>` +
      `<div><span>Nearest opponent</span><strong>${fact(nearest)} <small>m</small></strong></div>`;
  }

  function renderNarration(row) {
    const { metadata, frame } = getState();
    if (!row) { narration.textContent = ""; clockLabel.textContent = "\u2014"; return; }
    const player = metadata?.players?.find(item => item.player_id === row.actor_id);
    const team = metadata?.teams?.find(item => item.team_id === player?.team_id);
    clockLabel.textContent = formatClock(row.t_ms, metadata);
    const onPitch = frame?.players?.find(item => item[0] === row.actor_id);
    const owner = frame?.ball_owner_id === row.actor_id;
    const where = onPitch ? ` in the ${third(onPitch[1])}` : "";
    const who = team?.short_name || team?.name || "The player";
    narration.textContent = `${who} #${player?.jersey_number ?? ""} is ${owner ? "on the ball" : "receiving"}${where}.`;
  }

  // Which third of the pitch, in the attacking direction of the side in possession.
  function third(x) {
    const { metadata, frame } = getState();
    const period = metadata?.periods?.find(item => item.period === (frame?.period ?? 1));
    const positive = (period?.home_attacks ?? "positive_x") === "positive_x";
    const home = frame?.possession_team_id !== "AWAY";
    const attack = positive === home ? x : 105 - x;
    if (attack < 35) return "defensive third";
    if (attack < 70) return "middle third";
    return "attacking third";
  }

  function renderAnalysis() {
    const { metadata } = getState();
    const name = id => {
      const player = metadata?.players?.find(item => item.player_id === id);
      const team = metadata?.teams?.find(item => item.team_id === player?.team_id);
      return player ? `${team?.short_name || team?.name || ""} #${player.jersey_number}` : id;
    };
    const options = (doc.public?.candidates || doc.candidates || []).filter(item => item.eligible);
    const actor = bundle?.request?.actor_id;
    const label = doc.public?.status === "model_unavailable" ? "computed comparison" : (doc.public?.status || doc.status || "ready");
    const head = `<p class="ask-subject"><strong>${esc(name(actor))}</strong><span>${esc(label)}</span></p>`;

    // Coach mode withholds the reading until you commit to a choice. That is the
    // "pick first, then reveal" half of the brief, and it is the reason the
    // three-dimensional page was still carrying a mode this page now owns.
    if (mode === "coach" && !picked) {
      analysis.innerHTML = head +
        `<p class="ask-pick">Pick the option you would take. The comparison unlocks once you commit.</p>` +
        options.slice(0, 3).map(item =>
          `<button class="ask-choice" type="button" data-pick="${esc(item.action_id)}">` +
          `<strong>${esc(item.type)}</strong><small>${esc(item.action_id)}</small></button>`).join("");
      return;
    }

    const verdict = picked
      ? (() => {
          const chosen = options.find(item => item.action_id === picked);
          const rank = chosen?.rank;
          return `<p class="ask-verdict">You picked <b>${esc(picked)}</b>. ` +
            (rank === 1 ? "The model ranked it first." : `The model ranked it ${esc(String(rank ?? "outside the listed options"))}.`) +
            `</p>`;
        })()
      : "";
    analysis.innerHTML = head + verdict +
      options.slice(0, 3).map(item =>
        `<article${item.action_id === picked ? ' class="ask-yours"' : ""}><h4><span class="ask-rank">${esc(item.rank)}</span>${esc(item.type)}<small>${esc(item.action_id)}</small></h4>` +
        `<p>${esc(item.opportunity)}</p>` +
        `<p class="ask-risk">${esc(item.main_risk)}</p></article>`).join("");
  }

  function show(row, entry) {
    bundle = entry.bundle;
    doc = entry.doc;
    shownId = row.decision_id;
    picked = "";
    renderMeasures(bundle.request.actor_id);
    renderAnalysis();
    const { time, playing } = getState();
    const offset = time - row.t_ms;
    // Never let a stale read pass as the current frame.
    const age = offset > DECISION_WINDOW_MS + 500
      ? ` Nearest registered decision, ${(offset / 1000).toFixed(1)} s before this frame.`
      : "";
    status.textContent = playing
      ? "Following the playhead. Pause to ask a question about this moment."
      : `Paused on this decision.${age} Ask about these choices.`;
    form.hidden = playing;
  }

  function clearPanel(message) {
    shownId = "";
    bundle = doc = null;
    analysis.replaceChildren();
    measures.replaceChildren();
    answer.textContent = "";
    form.hidden = true;
    status.textContent = message;
  }

  async function follow(row) {
    const current = ++token;
    status.textContent = getState().playing
      ? "Reading this decision as the play moves…"
      : "Reading this decision…";
    try {
      const entry = await read(row);
      if (current !== token || row.decision_id === shownId) return;
      show(row, entry);
    } catch (error) {
      if (current === token) status.textContent = error.message;
    }
  }

  for (const button of document.querySelectorAll("[data-mode]")) {
    button.addEventListener("click", () => {
      mode = button.dataset.mode;
      picked = "";
      for (const other of document.querySelectorAll("[data-mode]")) {
        other.setAttribute("aria-pressed", String(other === button));
      }
      if (doc) renderAnalysis();
    });
  }

  analysis.addEventListener("click", event => {
    const choice = event.target.closest("[data-pick]");
    if (!choice) return;
    picked = choice.dataset.pick;
    renderAnalysis();
  });

  form.addEventListener("submit", async event => {
    event.preventDefault();
    const question = $("#ask-input").value.trim();
    if (!question || !bundle || !doc) return;
    const setId = doc.candidate_set_id || doc.public?.candidate_set_id;
    const request = { ...bundle.request, question, mode: "fan", language: "en" };
    answer.textContent = "Asking the four-role team…";
    try {
      const response = await fetch("/api/decision-analysis/agents", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ request, candidate_set_id: setId }),
      });
      const value = await response.json();
      if (!response.ok) throw new Error(value.error || "The question could not be answered.");
      const text = value.explanation?.text;
      answer.textContent = text || "The comparison above still stands. No language model is configured for this question.";
    } catch (error) {
      answer.textContent = error.message;
    }
  });

  return {
    setMatch(id) {
      matchId = id;
      index = null;
      cache.clear();
      clearPanel("Loading decisions for this match…");
      token += 1;
      narration.textContent = "";
      clockLabel.textContent = "—";
      loadIndex(id).then(value => {
        if (value.match_id !== matchId) return;
        index = value;
        status.textContent = "Move the replay onto a possession to read the choice set.";
        followLabel.textContent = `${value.records.length.toLocaleString("en-GB")} registered decisions`;
      }).catch(error => {
        status.textContent = error.message;
      });
    },
    showTeam(teamId) {
      showBoard(teamId === "AWAY" ? "away" : "home");
    },
    // Called on every UI tick. Narration follows the playhead at any speed; the
    // comparison follows it as fast as one read at a time allows.
    sync() {
      const { time, playing } = getState();
      if (!index) return;
      // Playing keeps the window tight so the read matches the picture. Paused,
      // a wider lookback is what lets the panel answer "what is happening now"
      // anywhere in the half, with the offset stated.
      const row = playing ? nearest(time) : nearest(time, PAUSED_LOOKBACK_MS);
      renderNarration(row);
      if (playing) followLabel.textContent = "Following the playhead";
      else followLabel.textContent = row ? "Paused on a decision" : "Paused";
      if (!row) {
        if (shownId) clearPanel(playing ? "No registered decision here." : "No registered decision in the last 30 s. Move the timeline onto a possession.");
        return;
      }
      if (row.decision_id === shownId) {
        // A read that arrived during playback left the question box closed.
        // Pausing on that same decision has to open it again.
        form.hidden = playing;
        if (!playing && bundle) status.textContent = "Paused on this decision. Ask about these choices.";
        return;
      }
      if (cache.has(row.decision_id)) show(row, cache.get(row.decision_id));
      else follow(row);
      warm(time);
    },
  };
}
