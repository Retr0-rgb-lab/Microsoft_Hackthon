"""Diagnostic section for the full system audit."""
import html
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path


def section(root):
    path=root/'artifacts/realism/system-validation.json'
    if not path.exists(): return ''
    r=json.loads(path.read_text());local_time=datetime.fromisoformat(r['generated_at_utc']).astimezone(ZoneInfo('Europe/London')).strftime('%Y-%m-%d %H:%M %Z');c=r['pipeline_counts'];games=r['matches'];n=len(games)
    rows=[]
    labels={'pass_distance_m':('Average ground-pass distance','m',1),'pass_completion':('Ground-pass completion rate','%',100),
            'backward_pass_share':('Backward-pass share','%',100),'shot_distance_m':('Average shot distance','m',1),
            'shot_conversion':('Shot conversion rate','%',100)}
    for key,(label,unit,factor) in labels.items():
        a,b=r['real_held_out'][key]*factor,r['synthetic'][key]*factor
        rows.append(f'<tr><th>{label}</th><td>{a:.2f}{unit}</td><td>{b:.2f}{unit}</td><td>{abs(a-b):.2f}{" percentage points" if factor==100 else unit}</td></tr>')
    rates=r.get('per90_selected_events',{})
    volume=''
    if rates:
        volume=f"<p class='note'>Per 90 minutes of match time, footed shots inside the selection range: real {rates['shots']['real']:.2f}, synthetic {rates['shots']['synthetic']:.2f}; footed ground passes: real {rates['passes']['real']:.1f}, synthetic {rates['passes']['synthetic']:.1f}. Action frequencies still differ noticeably. The synthetic set has no full play_pattern scene classification, so the frequency comparison is not on an identical basis and cannot be used to compare all match shots directly.</p>"
    contexts={key:sum(g['contexts'].get(key,0) for g in games) for key in ('no_forward_legal_target','selected_backpass','backpass_with_no_forward_target')}
    def percentage(value,total): return f'{100*value/max(1,total):.1f}%'
    models=[]
    for kind,m in r['real_outcome_model_metrics'].items():
        lo,hi=m['paired_match_bootstrap']['ci95']
        models.append(f'<tr><th>{kind}</th><td>{m["n"]}</td><td>{m["constant_train_prior_brier"]:.5f}</td><td>{m["brier"]:.5f}</td><td>[{lo:.5f}, {hi:.5f}]</td></tr>')
    zones=[]
    for z in r['zone_fit']:
        a,b=z['real'],z['synthetic']
        zones.append(f'<tr><th>{z["zone"]+1}</th><td>{a["passes"]}</td><td>{b["passes"]}</td><td>{a["backward_pass_share"]*100:.1f}%</td><td>{b["backward_pass_share"]*100:.1f}%</td></tr>')
    league_report=root/'data/league-validated/validation_report.json'
    integrity=json.loads(league_report.read_text()).get('status','unknown') if league_report.exists() else 'not run'
    return f'''<section><h2>Full league: system analysis and real-data fit check</h2><p>Run time (UK): {local_time} · {html.escape(r['generator_version'])} · {n} new matches. Every post-match report has been generated and the deterministic pass analysis has been run on each one; no paid LLM agent was called in bulk.</p><p><a href="coach.html?dataset=validated">Open these 40 new matches for analysis</a> · <a href="artifacts/realism/system-validation.json">Full system-check JSON</a> · <a href="artifacts/realism/system-analysis.jsonl">Per-decision analysis record</a></p><p>League consistency: {integrity}; {c['decisions']:,} decision records, {c['analyzed']:,} analysed, {len(r['analysis_errors'])} analysis errors; {c.get('unavailable',0)} final-snapshot records that cannot be analysed were rejected. All {c.get('cancelled_or_unresolved_actions',0)} unfinished actions were reconciled against cancellation events (substitutions, red cards, half-time or full-time). {c['rollout_runs']} short rollouts were run, four cases each, used only to check that the tool runs.</p><table><thead><tr><th>Metric</th><th>Real held-out reference (8 matches)</th><th>Full new league</th><th>Absolute gap</th></tr></thead><tbody>{''.join(rows)}</tbody></table>{volume}<h3>Structural check on route selection</h3><p>{percentage(contexts['no_forward_legal_target'],c['analyzed'])} of the analysed decision snapshots had no legal forward target. Of the selected backpasses, {percentage(contexts['backpass_with_no_forward_target'],contexts['selected_backpass'])} also had no legal forward target. This helps locate support problems but does not prove cause and effect. In {percentage(c['all_passes_negative'],c['analyzed'])} of the snapshots every legal pass had a negative value gain; the analyser only compares passes, so it cannot conclude that the player should have passed.</p><table><thead><tr><th>Attacking zone (own half → attacking third)</th><th>Real passes</th><th>Synthetic passes</th><th>Real backward-pass rate</th><th>Synthetic backward-pass rate</th></tr></thead><tbody>{''.join(zones)}</tbody></table><p>Distance-distribution JS distance (0 means identical, 1 means no overlap): passes {r['distance_distribution_js_distance']['pass']:.3f}, shots {r['distance_distribution_js_distance']['shot']:.3f}. This measures the difference between distance histograms, not an overall football-realism score.</p><h3>Real-outcome prediction: the score is checked again</h3><table><thead><tr><th>Model</th><th>Test events</th><th>Constant-baseline Brier</th><th>Calibrated-model Brier</th><th>Improvement, 95% interval</th></tr></thead><tbody>{''.join(models)}</tbody></table><p>The interval comes from resampling the 8 matches by whole match 2,000 times. The improvement is the constant-baseline error minus the model error, so a positive value favours the model. When the interval crosses zero, the improvement cannot be called stable. The data comes from a single competition, and the number of events is not the number of independent matches.</p><p class="note">Boundaries: these 8 test matches had been inspected before, so this is a reproduction and a scale check rather than a fresh blind test. Real pressure annotations and the synthetic 3-metre distance marker are not measured on the same basis. Real events can only validate outcome probabilities and event statistics; the route feasibility index, the counterfactual rollout and the run positioning on the analysis page have no real-tracking validation. The outcome score in the synthetic run is sampled by the generator itself, so internal consistency must not be read as real accuracy. Backpasses, ball-retention zones and support still need work.</p></section>'''
