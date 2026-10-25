"""Chinese diagnostic section for the full system audit."""
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
    labels={'pass_distance_m':('平均地面传球距离','米',1),'pass_completion':('地面传球完成率','%',100),
            'backward_pass_share':('回传比例','%',100),'shot_distance_m':('平均射门距离','米',1),
            'shot_conversion':('射门进球比例','%',100)}
    for key,(label,unit,factor) in labels.items():
        a,b=r['real_held_out'][key]*factor,r['synthetic'][key]*factor
        rows.append(f'<tr><th>{label}</th><td>{a:.2f}{unit}</td><td>{b:.2f}{unit}</td><td>{abs(a-b):.2f}{"个百分点" if factor==100 else unit}</td></tr>')
    rates=r.get('per90_selected_events',{})
    volume=''
    if rates:
        volume=f"<p class='note'>按比赛时间折算，筛选范围内每 90 分钟脚下射门：真实 {rates['shots']['real']:.2f} 次，模拟 {rates['shots']['synthetic']:.2f} 次；地面脚下传球：真实 {rates['passes']['real']:.1f} 次，模拟 {rates['passes']['synthetic']:.1f} 次。动作频率仍有明显差异；模拟没有真实 play_pattern 的完整场景分类，频率比较还存在口径差异，不能据此直接比较全部比赛射门。</p>"
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
    return f'''<section><h2>完整新版联赛：系统分析与真实数据拟合检查</h2><p>运行时间（英国）：{local_time} · {html.escape(r['generator_version'])} · {n} 场新比赛。全部赛后报告已生成，逐条运行确定性传球分析；未批量调用收费 LLM Agent。</p><p><a href="coach.html?dataset=validated">打开这 40 场新数据进行分析</a> · <a href="artifacts/realism/system-validation.json">完整系统检查 JSON</a> · <a href="artifacts/realism/system-analysis.jsonl">逐次决策分析记录</a></p><p>联赛一致性：{integrity}；决策记录 {c['decisions']:,} 条，已分析 {c['analyzed']:,} 条，分析异常 {len(r['analysis_errors'])} 条；{c.get('unavailable',0)} 条终场不可分析快照已拒绝。{c.get('cancelled_or_unresolved_actions',0)} 条未完成动作均已按取消事件核对（换人、红牌、半场或终场）。短时推演 {c['rollout_runs']} 次，每次 4 个情形，仅用于工具运行检查。</p><table><thead><tr><th>指标</th><th>真实独立 8 场参考</th><th>新版完整联赛</th><th>绝对差距</th></tr></thead><tbody>{''.join(rows)}</tbody></table>{volume}<h3>路线选择的结构性检查</h3><p>{percentage(contexts['no_forward_legal_target'],c['analyzed'])} 的决策快照中没有向前的合法接球队友。被选择的回传里，{percentage(contexts['backpass_with_no_forward_target'],contexts['selected_backpass'])} 同时没有向前合法目标。这有助于定位接应问题，但尚未证明因果。{percentage(c['all_passes_negative'],c['analyzed'])} 的快照中，全部合法传球的价值增益都为负；分析器只比较传球，不能据此认定球员应当传球。</p><table><thead><tr><th>进攻区域（后场→前场）</th><th>真实传球数</th><th>模拟传球数</th><th>真实回传率</th><th>模拟回传率</th></tr></thead><tbody>{''.join(zones)}</tbody></table><p>距离分布 JS 距离（0 表示相同，1 表示不重叠）：传球 {r['distance_distribution_js_distance']['pass']:.3f}，射门 {r['distance_distribution_js_distance']['shot']:.3f}。这衡量距离直方图差异，不是综合足球真实性分数。</p><h3>真实结果预测：重新核验评分</h3><table><thead><tr><th>模型</th><th>测试事件数</th><th>常数基线 Brier</th><th>校准模型 Brier</th><th>改善量 95% 区间</th></tr></thead><tbody>{''.join(models)}</tbody></table><p>区间由 8 场比赛按整场重采样 2,000 次计算；改善量为常数基线误差减模型误差，正值有利于模型。跨过 0 时，不能认为改善已稳定。只来自一个赛事，事件样本量不等于独立比赛数。</p><p class="note">边界：这 8 场测试此前已查看，本次是复现与规模检查，并非新盲测。真实受压标注与模拟 3 米距离标记的口径不同。真实事件只能验证结果概率与事件统计；分析页面的路线可行性指数、反事实推演和跑位没有真实轨迹验证。模拟中的结果评分是生成器自己抽样的结果，不能把内部自洽当成真实准确率。回传、球权区域与接应仍须改进。</p></section>'''
