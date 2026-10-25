"""Render the saved metrics into a local, inspectable diagnostics page."""
import html
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    r=json.loads((ROOT/'artifacts/realism/generator-comparison.json').read_text())
    v=json.loads((ROOT/'artifacts/realism/real-data-validation.json').read_text())
    labels={'pass_distance_m':('平均地面传球距离','米',1),'pass_completion':('地面传球完成率','%',100),
            'backward_pass_share':('回传比例','%',100),'shot_distance_m':('平均射门距离','米',1),
            'shot_conversion':('射门进球比例','%',100)}
    rows=[]
    for key,(label,unit,factor) in labels.items():
        values=[r[group][key]*factor for group in ('real_held_out','baseline','modified')]
        improved=r['absolute_gaps'][key]['after']<r['absolute_gaps'][key]['before']
        rows.append('<tr><th>'+label+'</th>'+''.join(f'<td>{value:.2f}{unit}</td>' for value in values)+f'<td>{"偏差缩小" if improved else "偏差扩大，待修正"}</td></tr>')
    before=sum(g['unpressured_large_backpasses_near_goal'] for g in r['baseline_matches'])
    after=sum(g['unpressured_large_backpasses_near_goal'] for g in r['modified_matches'])
    models=''.join(f'<tr><th>{kind}</th><td>{m["n"]}</td><td>{m["constant_train_prior_brier"]:.5f}</td><td>{m["brier"]:.5f}</td></tr>' for kind,m in v['predictive_metrics'].items())
    page='''<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>NextPlay 真实数据校准验证</title><style>body{font:17px/1.7 system-ui;background:#101e25;color:#e1ece6;max-width:1050px;margin:40px auto;padding:0 24px}a{color:#9edbbb}table{border-collapse:collapse;width:100%;margin:24px 0}th,td{padding:12px;border-bottom:1px solid #416056;text-align:left}section{background:#1c3037;padding:24px;margin:24px 0;border-radius:12px}.note{color:#ffd78c}code{overflow-wrap:anywhere}</style><a href="coach.html?realism=1">← 查看新版模拟样例</a><h1>真实数据校准与模拟验证</h1><p>生成器 v2.2.0 · 合成比赛；真实事件提供统计参考。未宣称最佳决策或职业级足球引擎。</p><section><h2>三场同种子比赛：修改前后对比</h2><p>种子：20261019、12345、712。下表的真实参考来自最终独立 8 场比赛；距离换算为 105 × 68 米球场。新版策略仅生成地面传球，避免把地面校准结果套用到高球。仅比较地面脚下传球、脚下射门。原模拟把部分不成功传球移向防守者，终点口径仍有差异。</p><table><thead><tr><th>指标</th><th>真实参考</th><th>旧生成器</th><th>新生成器</th><th>与真实参考差距</th></tr></thead><tbody>'''+''.join(rows)+f'''</tbody></table><p>门前无明显压力的大幅回传：{before} → {after} 次（3 场合计）。诊断定义：进攻坐标超过 88 米、向后超过 30 米、事件未标受压；策略的降权条件更严格，要求最近防守者超过 4 米。它不是“错误决策”的人工标签。</p><p class="note">整体回传比例仍然偏高，而且比旧版本更远离真实参考。这可能与固定阵型和强制带球把球推进到队友前方有关；下一步需要验证无球接应与球权区域分布。不能把局部指标改善说成全场战术已经真实。</p></section><section><h2>评分模型：独立真实比赛测试</h2><table><thead><tr><th>模型</th><th>事件数</th><th>常数基线 Brier</th><th>校准模型 Brier</th></tr></thead><tbody>'''+models+'''</tbody></table><p>Brier 是预测概率与实际结果的均方误差，越低越好。基线只使用训练集整体完成率／进球率。传球按距离与受压分组，射门按距离分组，使用平滑处理。没有用测试结果训练。</p><p class="note">最终测试只有 50 次脚下射门；进球率估计不稳定。评分改善不能证明反事实动作或球员跑位正确。</p></section><section><h2>数据来源、拆分与边界</h2><p>来源：<a href="https://github.com/statsbomb/open-data">StatsBomb Open Data / Hudl</a>，2022 世界杯。按 match_id 排序取前 32 场：16 场校准、8 场开发检查、另外 8 场最终测试。首轮开发结果已保留，最终测试未用于修改策略。</p><p>筛选：上下半场、Regular Play、脚下地面传球／脚下射门，并纳入 Carry。事件数并非等价决策机会，因此区域动作频率只是生成权重参考。样本不是英超代表性样本。</p><p>数据没有连续追踪，无法验证防守跑位、身体朝向、惯用脚、完整碰撞物理和未发生动作。仍然保留原先简化的射门扑救比例、不成功传球处理和重启后带球。新版分析页面的路线可行性指数仍是独立启发式模型，不是这次校准出的成功概率。</p><p>数据原始文件保存在本机 .local/statsbomb，不随项目公开分发； profile 与验证 JSON 记录源 URL、版本、校验值及训练／测试比赛 ID。公开发布数据衍生成果时，请遵循来源仓库条款并添加要求的 StatsBomb 标识。</p><p>数据版本：<code>'''+html.escape(v['source']['commit'])+'''</code></p><p><a href="artifacts/realism/real-data-validation.json">评分与来源 JSON</a> · <a href="artifacts/realism/generator-comparison.json">模拟对比 JSON</a> · <a href="artifacts/realism/initial-development-comparison.json">首轮开发对比</a></p></section></html>'''
    upgrade_path=ROOT/'decision/value-model.json'
    if upgrade_path.exists():
        upgrade=json.loads(upgrade_path.read_text());check=upgrade['validation']
        notice=f"<section><h2>新增：动作与决策分开评价</h2><p><a href='action-review.html'>打开动作分析升级页面</a> · <a href='artifacts/realism/action-upgrade-validation.json'>升级检查记录</a></p><p>真实事件训练的位置价值模型：同一简化球权下最多 10 个符合筛选条件的有球动作内进球。测试 {check['test_actions']} 个动作，{check['positive_goal_windows']} 个重叠进球窗口（不是独立进球数）；Brier {check['brier']:.6f}，常数训练基线 {check['constant_train_baseline_brier']:.6f}。只说明位置价值有初步依据，不代表替代选择排名已验证。</p><p>传球、带球、射门、等待使用同一价值单位。线路防守调整和带球／等待保有球权仍是规则假设。敏感性范围不是置信区间。实际执行结果单独按回放时间揭示，不会反向改变事前评分；没有姿态和触球信息时，不给技术质量分。</p></section>"
        page=page.replace('<section>',notice+'<section>',1)
    from .render_system import section
    page=page.replace('<section>',section(ROOT)+'<section>',1)
    refresh_path=ROOT/'artifacts/realism/data-refresh.json'
    if refresh_path.exists():
        refresh=json.loads(refresh_path.read_text())
        rows=''.join(f'<tr><th>{label}</th><td>{refresh["action_mix"]["shares"][kind]*100:.2f}%</td><td>{refresh["real_test_shares"][kind]*100:.2f}%</td></tr>'
                     for kind,label in (('pass','传球'),('carry','带球'),('shot','射门')))
        notice=f'''<section><h2>当前数据：球员属性策略已应用</h2><p>{html.escape(refresh['generator'])} · {refresh['matches']} 场比赛 · {refresh['players']} 名球员。保留赛程和随机种子，重新计算结果、积分榜、热力图、决策和赛后分析。以下是当前完整联赛的动作占比，排除了重启后的强制带球。</p><table><thead><tr><th>动作</th><th>当前联赛</th><th>真实测试参考</th></tr></thead><tbody>{rows}</tbody></table><p>参考为世界杯数据中的地面传球、带球和脚下射门，分母仅包含这三类动作。匹配占比不代表全部动作、每分钟数量或个人风格已获验证。</p><p><a href="artifacts/realism/data-refresh.json">本次数据更新记录</a> · <a href="artifacts/realism/player-action-validation.json">独立种子校准验证</a></p></section>'''
        page=page.replace('<section>',notice+'<section>',1)
        page=page.replace('生成器 v2.2.0 · 合成比赛','生成器 v2.3.0 · 合成比赛')
        page=page.replace('三场同种子比赛：修改前后对比','历史 v2.2 校准记录：三场同种子比赛对比')
    (ROOT/'realism-validation.html').write_text(page)

if __name__=='__main__': main()
