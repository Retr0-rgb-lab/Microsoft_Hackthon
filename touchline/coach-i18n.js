// Display localization only. Never changes identifiers, scores or exported evidence.
const pairs = [
['Previous controlled moment','上一个明确持球时刻'],['Next controlled moment','下一个明确持球时刻'],
['Ball controlled: pass analysis is available.','当前持球者明确，可以分析传球选择。'],
['Controlled moment selected. Analyze to compare passes.','已定位明确持球时刻，点击分析即可比较传球。'],
['No tracking snapshot loaded.','尚未加载位置快照。'],
['Play is stopped. Jump to a moment when a player controls the ball.','当前比赛暂停，请跳到球员明确持球的时刻。'],
['The ball is in flight. Pass-choice analysis requires a player in control; jump to the next controlled moment.','当前球在传球或射门途中。传球选择分析需要明确持球者，可跳到下一个持球时刻。'],
['Ball control is not recorded in this frame. Jump to another controlled moment; no owner is inferred.','此帧没有记录明确持球者，请跳到其他持球时刻；系统不会猜测球权。'],
['SYNTHETIC FOOTBALL · RESEARCH BASELINE','合成足球数据 · 研究原型'],
['Why not pass to them?','为什么不传给他？'],['Freeze a moment. Compare the routes. Inspect the evidence.','暂停一个时刻，比较路线，查看判断依据。'],
['Match','比赛'],['Explanation','解释模式'],['Casual fan','普通球迷'],['Analyst','分析师'],
['Analyze this moment','分析当前时刻'],['Export evidence','导出分析证据'],['Preview time','比赛片段时间'],
['Simulate selected pass','推演所选传球'],['Assumption','推演假设'],['Play / replay hypothesis','播放／重播假设推演'],['Return to snapshot','返回原始快照'],['Hypothesis time','推演时间'],
['No counterfactual loaded. Actual replay and hypothetical motion are separate.','尚未加载假设推演。比赛回放与假设运动分开展示。'],
['Blue: HOME · orange: AWAY · white ring: ball owner. Click a route in the table to inspect it. Dashed routes are offside.','蓝色：主队 · 橙色：客队 · 白圈：持球者。点击表格中的路线查看依据，虚线表示越位选项。'],
['What are the options?','当前有哪些选择？'],['Loading match previews…','正在加载比赛片段…'],['Choose a moment, then analyze.','选择比赛时刻，再点击分析。'],
['Ask the analysis team','向分析团队提问'],['Your question','你的问题'],['Run model agents','运行模型 Agent'],['Touchline Settings','Touchline 设置'],
['Four model contexts: coordinator → attack → defense → reviewer. Uses the model saved in','四个独立模型上下文：协调 → 进攻 → 防守 → 证据审查。使用以下位置保存的模型：'],
['. Running sends this synthetic snapshot, your question and computed evidence to that provider and may incur API charges. Up to 14 model requests; up to about 150 seconds. The model runs on Azure AI Foundry. The orchestration is a custom four-role workflow over the Responses tool loop, not the Microsoft Agent Framework graph.','。运行时会将合成快照、你的问题和计算证据发送至所配置的服务，可能产生 API 费用。最多 14 次模型请求，约 150 秒。模型运行在 Azure AI Foundry 上；编排是基于 Responses 工具循环的自定义四角色工作流，不是 Microsoft Agent Framework 图。'],
['No model agents have run for this snapshot.','当前快照尚未运行模型 Agent。'],['No model agents have run for this selected route.','所选路线尚未运行模型 Agent。'],
['Actual handoffs, tool calls and cited evidence','实际交接、工具调用与引用证据（原始记录）'],
['Pass to','接球者'],['Rule check','规则检查'],['Feasibility index','可行性指数'],['Value gain','价值增益'],['Critical defender','关键防守者'],['Eligible','符合当前规则检查'],['Offside','越位'],
['Model assumptions & research','模型假设与研究依据'],['un-xPass paper','un-xPass 论文'],['Pitch Control reference','空间控制模型参考'],
['This baseline uses probability-weighted outcome values minus current value, following the expected-usefulness formulation in un-xPass §2.1. Its feasibility and spatial-value functions are hand-defined and uncalibrated. They are not trained un-xPass, VAEP, xT, xG, or real goal probabilities. Player foot preference and body orientation are unknown. Only candidate ground passes are compared; the result does not claim passing is better than shooting or carrying.','本原型参考 un-xPass 第 2.1 节的期望效用结构，将不同结果加权后减去当前价值。可行性与空间价值函数为手工设定，尚未校准，并非训练后的 un-xPass、VAEP、xT、xG 或真实进球概率。惯用脚和身体朝向未知。目前仅比较候选地面传球，不代表传球优于射门或带球。'],
['Workflow: deterministic Python stages. No LLM or multi-agent execution is claimed.','基础分析由确定性 Python 程序完成。只有主动运行模型 Agent 后，才会产生真实模型调用记录。'],
['Computed · best among evaluated ground passes only','计算完成 · 排名仅限已比较的地面传球'],
['Snapshot changed. Analyze again.','快照已变化，请重新分析。'],['Explanation mode changed. Analyze again.','解释模式已变化，请重新分析。'],['Evaluating routes and interception margins…','正在计算路线与拦截时间余量…'],
['Simulating four bounded hypotheses…','正在计算四种短时假设…'],['Showing original snapshot. Hypotheses remain available to replay.','当前显示原始快照，仍可重播假设推演。'],
['Enter a question first.','请先输入问题。'],['Model workflow running. Trace will appear when the bounded review finishes. Changing the snapshot discards its answer.','模型团队正在运行，完成后显示调用记录。更换快照后会丢弃本次答案。'],
['Configure a Responses-compatible model and API key in Settings. No model agents ran.','请先在设置中配置支持 Responses 的模型和 API key。本次没有运行模型 Agent。'],
['Requires an in-play snapshot with a known ball owner.','需要比赛进行中且持球者明确的快照。'],
['No legal pass candidate in this snapshot. Other action types are not evaluated.','此快照没有可用的合法传球候选，尚未评价其他动作。'],
['Agent review did not complete. Computed baseline remains available; inspect partial trace.','Agent 审查未完成，基础计算仍可用，请查看部分调用记录。'],
['Same outcome in these four cases; this does not establish reliability outside them.','四种情形结果相同，但不能证明其他条件下也可靠。'],['Outcomes differ across assumptions: this option is sensitive to the tested conditions.','不同假设得到不同结果，该选项对所测试条件较敏感。'],
['These cases are not probability estimates.','这些案例不代表概率估计。'],['This compares modelled options, not what would certainly happen.','这里比较的是模型选项，不是必然发生的结果。'],
['Even the highest-ranked pass has negative estimated gain; holding, carrying and shooting have not been evaluated.','即使排名最高的传球，估计增益仍为负；尚未比较护球、带球和射门。'],
['Uncalibrated model indices; not real success or goal probabilities.','模型指数尚未校准，不是真实成功率或进球概率。'],
['negative means the defender may arrive before the ball','负值表示防守者可能先于球到达'],['false','否'],['true','是']
];
const dictionary = new Map(pairs);
export function translate(text, language) {
  if (language !== 'zh') return text;
  const trim = text.trim();
  if (dictionary.has(trim)) return text.replace(trim, dictionary.get(trim));
  let result = text;
  for (const [en, zh] of pairs) if (en.length > 20) result = result.split(en).join(zh);
  return result
    .replace(/Among evaluated passes, (\w+) has the highest model value\./g,'已比较传球中，$1 的模型价值最高。')
    .replace(/(\w+) is the critical defender along that route\./g,'$1 是这条线路的关键防守者。')
    .replace(/Pass to (\w+)/g,'传给 $1').replace(/Value gain =/g,'价值增益 =')
    .replace(/Defender arrival margin:/g,'防守者到达时间差：').replace(/Offside at release:/g,'出球时越位：')
    .replace(/\bfalse\b/g,'否').replace(/\btrue\b/g,'是')
    .replace(/Owner (\w+|unknown) · (\w+) · (.+)\. Only this snapshot is submitted for analysis\./g,'持球者 $1 · $2 · $3。仅提交此快照用于分析。')
    .replace(/HYPOTHESIS/g,'假设推演').replace(/Not actual match footage\./g,'并非实际比赛后续。')
    .replace(/\bquick\b/g,'快速反应').replace(/\bbaseline\b/g,'基准反应').replace(/\bdelayed\b/g,'延迟反应').replace(/\bwide_error\b/g,'落点偏移')
    .replace(/\bintercepted\b/g,'被拦截').replace(/\bunreceived\b/g,'未接到').replace(/\breceived\b/g,'接到').replace(/\bunresolved\b/g,'尚未结束')
    .replace(/ · reaction /g,' · 反应时间 ').replace(/ · pass offset /g,' · 传球偏移 ').replace(/ by (\w+)/g,'，控球者 $1')
    .replace(/ · period /g,' · 半场 ').replace(/Status: /g,'状态：').replace(/model requests: /g,'模型请求次数：').replace(/all four agents completed: /g,'四个 Agent 均完成：')
    .replace(/\bnot_configured\b/g,'未配置').replace(/\bcomplete\b/g,'已完成').replace(/\bpartial\b/g,'部分完成').replace(/\bfailed\b/g,'失败').replace(/\byes\b/g,'是').replace(/\bno\b/g,'否')
    .replace(/Gain /g,'增益 ').replace(/feasibility index /g,'可行性指数 ').replace(/minimum defender arrival margin /g,'最小防守到达时间差 ');
}
export function setupLanguage() {
  const picker = document.querySelector('#language');
  // English is the shipped default; the toggle keeps Chinese available.
  let language = 'en';
  try { const saved = localStorage.getItem('nextplay-language'); if (['en','zh'].includes(saved)) language = saved; } catch {}
  const original = new WeakMap();
  function update() {
    observer.disconnect();
    document.documentElement.lang = language === 'zh' ? 'zh-CN' : 'en';
    document.title = language === 'zh' ? 'NextPlay · 为什么不传给他？' : 'NextPlay · Why not pass?';
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      if (node.parentElement.closest('script,style,pre,svg,#agent-answer,#agent-caveats,#language')) continue;
      const old = original.get(node);
      const source = old && node.nodeValue === old.display ? old.source : node.nodeValue;
      const display = translate(source,language);
      original.set(node,{source,display});
      if (node.nodeValue !== display) node.nodeValue = display;
    }
    observer.observe(document.body,{subtree:true,childList:true,characterData:true});
  }
  const observer = new MutationObserver(update);
  picker.value = language;
  picker.onchange = () => {
    language = picker.value;
    try { localStorage.setItem('nextplay-language',language); } catch {}
    update(); window.dispatchEvent(new CustomEvent('nextplay-language',{detail:language}));
  };
  update(); return () => language;
}
