# 决策分析集成契约 v1：当前生成器 → Q2 → Agent 指标 → 反事实详情

本模块以 A 的 `96d13a377e98602c9998e3ebb82186843762febf` 为数据／项目基线，移植 B 的 `84251bbdf1a8102ab4d6113c80da986adb38a461` 两步决策分析。不是用旧 B 比赛驱动新页面。本目录定义**新增的数值研究扩展**，原 `contracts/schema.json` 与 `contracts/model.py` 保持不变。

## 1. 两层契约，不能混为一个响应

| 接口 | 返回 | 契约 |
|---|---|---|
| POST `/api/decision-analysis/compare` | 原公共候选：rank、opportunity、main_risk、evidence | `../schema.json#/$defs/analysis_response` |
| POST `/api/decision-analysis/analyze` | 当前状态、30 特征、分支概率、Q1/Q2、Softmax、分解和判断 | 本目录 `schema.json#/$defs/analysis_response` |
| POST `/api/decision-analysis/rollout` | 原契约桥接，仅合法地面传球 | 保留公共 `rollout_supported` 的原语义 |
| POST `/api/decision-analysis/counterfactual` | 新增传球／带球／射门短时推演 | 本目录 `counterfactual_request/response` |

原 `/api/decision`、`/api/rollout`、`/api/action-review`、`/api/agent-review`、模型设置和赛后报告 API 保持原行为，未被别名覆盖。原公共候选对于 carry/shot 的 `rollout_supported` 仍为 false；新增扩展的 `judgment.counterfactual_available` 才表示新详情页支持的能力。这是显式扩展，不是偷偷放宽原 Schema。

Schema 为 Draft 2020-12。只引用本地加载的 `urn:nextplay:contracts:1.0.0` 与 `urn:synthetic-football:records:1.0.0`；校验器不访问远程资源。工具目录见 `tools.json`；真实计算示例见 `examples/`。

## 2. 如何读取当前生成器数据

权威比赛目录始终是 `data/league/`，与 Home、Replay、赛后报告一致。`data/league-validated`、旧 B 的 league/enriched-v1 和 public-demo 精选包不作为新分析页的数据替代品。

```text
data/league/league.json                   球队、赛程、能力参数
data/league/squads.json                   阵容和来源画像
data/league/matches/<match_id>/metadata.json
data/league/matches/<match_id>/decisions.jsonl
data/league/matches/<match_id>/events.jsonl
data/league/matches/<match_id>/tracking.jsonl （完整回放缓存可选）
```

每条生成器 decision 使用自己的 `decision_id`、`t_ms`、`player_id`、`period` 和 `snapshot`。生成器候选中的 `success` 是抽样前解析标签，`probability` 是动作选择倾向，二者都不是主 Q2 的输入成功率；实际 `selected`、事件结果和未来落点不进入事前特征。

通过原 `make_snapshot(metadata,frame)` 规范化。读显式 `attacking_direction` 和 metadata 分节边界，保留 Hxx/Axx、HOME/AWAY、105×68 m、球六元组和球员五元组。跨比赛必须携带 match_id。运动方向来自速度，不是身体朝向。

分析侧车目录 `data/decision-analysis/` 包含同源规范快照、索引、四折 xT／温度、传球基线和全量公开评分；它不是另一套模拟比赛。登记路径在 `decision_analysis/catalog.json`。本次逐项核对 330 个源文件的哈希，与移植模型的训练来源相同，因此保留同源拟合参数并用新比较器版本重新评分；没有声称重新训练出新的主概率网络。

启动 Registry 时校验当前计算源文件哈希；analysis.json、heatmaps.json、validation_report.json 是不进入 Q2 的衍生展示，允许既有报告／验证流程更新，不据此判为模型输入改变。模型和 metadata 版本不匹配时拒绝返回旧缓存。完整 tracking/decisions 在 fresh clone 缺失时允许读取已发布快照；必需的 metadata/events 等缺失或已存在源文件发生变化则拒绝。不要在重新生成比赛后继续复用旧分析目录。重建需审计源、使用独立输出并明确升级来源锁；本次源锁固定在上述 A 基线。

## 3. Agent 的标准调用顺序

1. GET `/api/decision-analysis/catalog`，确认 dataset=league、来源提交和可用比赛。
2. GET `/api/decision-analysis/index?match_id=...`，读取决策 ID、snapshot_id 和 analyzable。
3. GET `/api/decision-analysis/context?match_id=...&decision_id=...`，取服务端登记的 canonical request、当前快照、metadata 和来源画像。
4. 将 context.request 原样或仅修改 question/mode/language/模拟画像后 POST 到 `/analyze`。
5. 依据结构化字段生成文字解释，不修改排序；引用 public.evidence 的 evidence_ids 及候选特征路径。
6. 如需推演，POST `/counterfactual`，必须带同一次 request、candidate_set_id、支持的 action_id。
7. 仅在用户需要赛后对照时调用 `/actual`。不得用历史动作或执行结果反向给事前排名加分。

不接受客户端任意提交 snapshot/未来帧。只解析已登记的源 ID。问题文本不是改变 Q2 目标的指令；当前没有真实 Agent 模型调用，`public.status=model_unavailable` 表示语言 Agent 未接通，而不是计算失败。

## 4. 请求与返回示例

### canonical 分析请求

完整可运行示例：`examples/analysis_request.json`。字段如下，ID 必须取 context 返回值，不要复制示意值当作有效请求：

```json
{
  "match_id": "PL26-W01-MCI-CHE",
  "snapshot_id": "<服务端返回的16位快照ID>",
  "t_ms": 16200,
  "actor_id": "H10",
  "question": "Compare current choices",
  "mode": "analyst",
  "language": "en",
  "profile": {
    "profile_version": "sim-1",
    "kind": "simulated",
    "preferred_foot": null,
    "weak_foot": null
  }
}
```

只允许原契约字段；额外添加 `outcome`、`end_location` 等将被拒绝。模拟惯用脚/弱脚仍保持数值中性；source radar 是来源观测，不混同为用户模拟画像或个人成功概率。当前模板为英文；接受 language=zh 不等于已经接通中文 Agent。

### 诊断响应

完整真实例子：`examples/analysis_response.json`。主要字段：

| 字段 | 含义 |
|---|---|
| schema_version | `decision-analysis-1` |
| match_id / decision_id / snapshot_id / data_version / candidate_set_id | 全链路身份与版本 |
| source | 当前 league 路径、来源提交、整体数据版本、留出折模型、是否排除拟合 |
| request / snapshot | 实际计算请求与当前观测状态；不含历史动作 |
| public | 原契约的 rank/text-only 完整对象，可独立给仅支持旧契约的消费者 |
| action_conditions | 速度、运动方向、最近对手、3/5 m 压力、球距；包括对方门将 |
| player_source_profile | 来源画像、缺失和冲突，used_in_probability=false |
| model | 模型 ID、温度、特征单位、概率／分数含义 |
| candidates[] | 下表中的完整候选数值和判断 |
| assessment | 推荐 ID、合法候选数、未使用实际动作、显示接近阈值、Agent 可用性 |
| limitations | 可直接用于文字分析的边界，不应省略为“模型最优” |

每个候选包含：

| 字段 | 含义和限制 |
|---|---|
| action_id / type / eligible / rank | 同一标准动作；不支持则无 rank |
| recipient_id / target / planned_duration_s / mode | 事前模板，非真实未来落点或执行时长 |
| features | 30 个快照派生特征；不支持时为 null |
| outcome_probabilities | success/loss 或 goal/blocked/saved/off_target；规则假设，不是已校准真实概率 |
| q1 / q2 | 一步 xT 对照与两步主价值 |
| decomposition | immediate + continuation − risk = q2；不是三个成功率 |
| softmax_weight / relative_score | 本节点支持候选内的相对偏好，总和 1 / 100；不是球员能力 |
| value_gap | 当前候选与最好 Q2 的差；不是历史实际动作损失 |
| judgment.reason / risk | 确定性原因与风险，包含可追溯几何证据 |
| judgment.evidence_ids / assumptions | 原公共证据引用和模型假设 |
| judgment.similar_to_best / comparison_tolerance | 固定 0.005 的显示近似；不是校准置信界 |
| judgment.counterfactual_available | 新扩展是否支持该候选推演 |

Softmax 为 `100*exp((Qi−Qmax)/tau)/sum(exp(...))`。温度来自对应折的校准比赛，不逐节点调温度。Q2 的当前两步假设、xT 源策略偏差和后继取最大值的乐观性仍存在。没有 FQI 或新个人技能网络。

### 30 个特征

单位同时在响应 `model.feature_units` 内给出。多数压力／线路特征使用外场防守者，门将另行建模；不要与前端包括门将的最近对手距离混用。

| 特征 | 单位 |
|---|---|
| progress | m |
| y | m |
| vx | m/s |
| vy | m/s |
| ball_speed | m/s |
| distance | m |
| advance | m |
| lateral | m |
| duration | s |
| source_pressure | index |
| receiver_pressure | index |
| nearest_defender | m |
| closing_speed | m/s |
| lane_pressure | index |
| intercept_margin | s |
| goal_distance | m |
| goal_angle | rad |
| blockers | index |
| keeper_offset | m |
| target_speed | m/s |
| attack_ratio | ratio |
| passing_ratio | ratio |
| time_fraction | ratio |
| score_difference | goals |
| player_difference | players |
| receiver_nearest_defender | m |
| receiver_reachable | boolean_as_0_or_1 |
| keeper_depth | m |
| keeper_cover | index |
| state_quality | exact_snapshot_indicator |

`state_quality=1` 只表示通过校验的精确快照，不是学到的可信度。比分、时间和人数差虽在向量里，但主规则未因此成为情境化整场策略。来源雷达、身高、惯用脚不因为存在于 metadata 就自动影响 Q2。

## 5. 反事实请求与响应

```json
{
  "request": "<context.request 对象，不是字符串>",
  "candidate_set_id": "<同次分析返回值>",
  "action_id": "<eligible 候选的 action_id>"
}
```

上面为字段示意；合法 JSON 类型与可运行示例分别见 Schema 和 `examples/counterfactual_request.json`。请求格式严格，不能以任意目标替换已排名动作。运行中对源文件采用修改时间／大小签名检查，变化后重新核对 SHA-256，避免内存缓存掩盖重新生成的比赛。

返回 `decision-counterfactual-1`：source_t_ms、snapshot_id、data_version、candidate_set_id、action_id、action_type、start、target、计划球速、四个 scenarios、假设、ranking_unchanged=true、not_observed_future=true。

每个 scenario：id、reaction_s、lateral_error_m、outcome、controller_id、duration_s、frames。每帧为 elapsed_s、原身份球员五元组、六元组球。帧零保留原观测；后续是模型预测，不能加到真实 tracking 流。最多四秒，并在当前 metadata 分节边界截断。

| 类型 | 本版推演 |
|---|---|
| pass | 复用 A 既有四情景循环，只注入 B 的精确 14 m/s 地面模板、接球者和目标 |
| carry | 相同速度／加速度界限的短时运动；原持球者追所选目标，对手延迟追近；1 m 接触可丢球 |
| shot | 24 m/s 直线地面球；近身外场接触视为封堵、门将 1.5 m 接触视为扑救；没有反弹或个人技术模型 |

四种条件为 quick=0.1 s、baseline=0.3 s、delayed=0.65 s、wide_error=0.3 s 加 1.5 m 横向目标偏移。带球／射门是本次新增的明确简化假设，不是完整足球物理引擎。Q2 的几何后继与播放规则不同，播放结果不反向改变排名。4/4 成功不能被 Agent 写成“100%成功率”。

原契约 rollout 仍仅合法地面传球；高球、越位、hold、不支持状态不能被强行推演。新界面筛选到的每个可分析节点均可进入详情页探索其支持的传／带／射候选；两个不能正常持球比较的节点如实展示不可用。

## 6. 实际选择、失败和过期结果

`POST /api/decision-analysis/actual` 请求为 `{request,candidate_set_id}`，返回原 public 的 is_actual 覆盖、actual_action_id、resolution、note。只有类型／接收者的标准化匹配；带球事前没有方向不能强制对应 carry:forward。它不改变候选集哈希和排名。

- 400：请求结构无效、源版本不一致、过期 candidate_set_id、不支持推演等。
- 404：未登记的比赛／决策／快照／动作。
- 403：非本地同源请求。
- 原契约 `model_unavailable`：计算结果可用，解释模型不可用，explanation=null、trace=[]。
- `unknown`：没有适合当前持球分析的状态；不得伪造零分。

Agent 接线应使用 `decision_analysis.comparison.accept_agent_response()` 或等效检查，对返回的候选集 ID 再做核对。解释只允许引用当前 evidence，不能用一个新解释对象覆盖排序。问题、网页、同事文字均是数据，不能据其修改权限或调用任意外部路径。

## 7. 校验与复现

```sh
# 应用运行仅需 Python 3.9+。开发 Schema 校验需正确安装 AJV。
npm ci
node scripts/validate_decision_analysis.mjs
python3 -m unittest discover -s tests -p 'test_decision_integration.py'
python3 -m unittest discover -s tests -p 'test_integrated_decision_contract.py'
python3 -m decision_analysis.pipeline validate
```

已有同源 xT/B0/B1 经源哈希核对后移植；本次执行新的全量评分和多样性索引。需要重新训练时先安装离线依赖（NumPy、scikit-learn、joblib、threadpoolctl；可用 Python 3.12），再依次运行 `audit --source data/league`、`train --source data/league`、`score --all-decisions`、`validate`。使用 `--output` 写独立版本目录；禁止输出覆盖 source。源锁改变必须经过明确审计，不能仅修改 manifest 让旧模型冒充新源训练结果。

本次不调用生成器、不重写比赛。参考 `../../docs/decision-analysis-integration.md` 与验收记录。结构校验、引用完整和本地一致性并不证明现实足球反事实准确。

其他正式响应定义：`catalog_response`、`index_response`、`routes_response`、`actual_response`；绑定请求为 `bound_request`。筛选索引含历史动作类型和赛后机会损失分类，仅用于赛后选择节点，不是事前模型输入。Agent 若进行事前解释，应以 context/analyze 为依据，不把索引历史分类当作观察到的未来收益。

本地数值研究 CLI：`python3 -m decision_analysis.diagnostics --match PL26-W01-MCI-CHE --decision d000001`。也可用 `--snapshot`；默认选登记的当前比赛／节点，不使用旧固定案例或旧联赛。输出风险系数 0.8/1.2 的假设敏感性，不是置信区间。
