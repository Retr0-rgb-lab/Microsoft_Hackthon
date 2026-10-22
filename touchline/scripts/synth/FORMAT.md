# 合成足球数据格式 v0.1（草案）

生成器：`generate.py`（单场模式，只依赖标准库）　校验：`validate.py`　Schema：`schema.json`（JSON Schema 2020-12）

所有球队、球员、场馆均为虚构。`validate.py` 用 `forbidden_terms.txt`（650 条：真实俱乐部、球场、联赛、品牌、真实球员姓名）做全词扫描，命中即失败。

## 1. 坐标系（写死）

| 项 | 约定 |
|---|---|
| 原点 | 中圈中心点（开球点） |
| 单位 | 米；速度 m/s；时间 ms；角度弧度 |
| 场地 | 105 × 68 |
| x | 沿长边，范围 [-52.5, 52.5]；两个球门中心在 (±52.5, 0)，门宽 7.32 |
| y | 沿宽边，范围 [-34, 34]；与 x、z 构成右手系（俯视时 +x 向右则 +y 向上） |
| z | 向上，地面 = 0 |
| facing | 弧度，取值 (-π, π]；0 表示朝 +x，逆时针为正（π/2 朝 +y） |
| attack_dir | 每帧都有。+1 表示**主队（HOME）**本帧向 +x 进攻，-1 表示向 -x 进攻；客队方向始终相反。v0.1：上半场 +1，下半场 -1 |
| frame_hz | 写在 metadata 里，默认 25，最低 10（`--hz`） |

## 2. 文件

| 文件 | 内容 |
|---|---|
| `metadata.json` | 比赛元数据：frame_hz、duration_ms、frame_count、coordinate_system、periods、teams、players、columns、limitations |
| `tracking.jsonl` | 每行一帧，共 `duration_ms/1000*frame_hz + 1` 行 |
| `events.jsonl` | 事件流，按 `available_at_ms` 单调递增，`sequence` 从 1 开始连续 |
| `states.jsonl` | 每秒一条比分和累计统计快照 |
| `summary.json` | 汇总（终场比分、事件计数、跑动距离等） |
| `validation_report.json` | `validate.py` 输出 |

## 3. tracking 帧

| 字段 | 类型 | 说明 |
|---|---|---|
| frame_id | int | 从 0 开始连续 |
| t_ms | int | `round(frame_id*1000/frame_hz)` |
| period, period_ms | int | 半场编号及半场内时间（每半场 50 分钟） |
| attack_dir | +1/-1 | 见坐标系 |
| in_play | bool | 死球（重新开球准备阶段）时为 false |
| phase | enum | carry / pass / shot / restart_setup / ended |
| action_id | str | 当前动作 |
| possession_team_id | HOME/AWAY/null | |
| ball_owner_id | str/null | 持球人；不为空时球距其 ≤0.6 m |
| score | [主, 客] | |
| players | 22 × `[player_id, x, y, vx, vy, facing]` | 列定义见 `metadata.columns` |
| ball | `[x, y, z, vx, vy, vz]` | 出界瞬间球可越线，最多越出 3 m |

## 4. 事件

公共字段：`event_id, sequence, match_id, type, period, period_ms, start_ms, end_ms, available_at_ms, possession_id`，可选 `team_id, related_event_ids`。所有 `*location` 字段都是 `[x, y]`，使用上面的坐标系。

| type | 关键字段 |
|---|---|
| decision_point | `player_id, location, xt_start, options[], chosen_index, chosen_option_id, policy`。在每次持球决策时发出（`available_at_ms` 等于随后动作的 `start_ms`） |
| ↳ option | `option_id, type(pass/carry/shot), target_player_id, end_location, success_prob, progress_m（朝进攻方向的推进距离）, xt_end, xt_gain, offside, offside_margin_m` |
| pass | `player_id, recipient_id`（意图接球人）, **`actual_receiver_id`**（实际接到的人：被断时为对方球员，出界时为 null）, `outcome`（complete / intercepted / out / offside）, `under_pressure, pass_height, start_location, end_location, decision_event_id` |
| carry | `player_id, start_location, end_location, decision_event_id`（重新开球后的第一次带球没有决策点） |
| shot | `outcome`（goal / saved / off_target）, `xg, score` |
| offside | `player_id`（越位球员）, `location`（传球瞬间的位置）, `offside_margin_m, pass_event_id`；随后是 stoppage 和 indirect_free_kick |
| ball_out | `line`（touchline / goal_line）, `location, last_touch_team_id, next_restart`（throw_in / corner / goal_kick）, `restart_team_id` |
| restart | `restart_type`（kick_off / throw_in / corner / goal_kick / indirect_free_kick / keeper_restart）, `player_id` |
| 其他 | possession_change, interception, pressure（3 m 范围内的距离标签）, save, stoppage, action_cancelled, period_start/end, match_end |

越位规则（简化的第 11 条）：传球瞬间接球人同时满足以下三条即越位——在对方半场、位置比球更靠前、位置比对方倒数第二名球员更靠前。用进攻方向坐标表示：`X_att > max(倒数第二名防守球员, 球, 0)`。

出界后的恢复：越过边线由对方掷界外球；越过底线时，最后触球的是守方则判角球，否则判球门球。

## 5. 读取示例：前端（three.js）

```js
import * as THREE from 'three';
const meta = await (await fetch('sample/metadata.json')).json();
const frames = (await (await fetch('sample/tracking.jsonl')).text())
  .trim().split('\n').map(JSON.parse);          // 大文件建议放到 Worker 里流式解析
// 数据坐标系 (x 长边, y 宽边, z 上) -> three.js (Y 朝上)：X=x, Y=z, Z=-y
const toScene = (x, y, z = 0) => new THREE.Vector3(x, z, -y);
const meshes = {};                               // player_id -> Mesh，预先创建 22 个 + 1 个球
function render(tMs) {
  const k = tMs * meta.frame_hz / 1000, i = Math.floor(k), a = k - i;
  const f0 = frames[i], f1 = frames[Math.min(i + 1, frames.length - 1)];
  f0.players.forEach(([id, x, y, vx, vy, facing], j) => {
    const [, x1, y1] = f1.players[j];
    meshes[id].position.copy(toScene(x + (x1 - x) * a, y + (y1 - y) * a));
    meshes[id].rotation.y = facing;              // 绕 Y 轴；数据 0 = +x，逆时针为正，转换后方向一致
  });
  const [bx, by, bz] = f0.ball;
  meshes.ball.position.copy(toScene(bx, by, bz + 0.11));
  // 主队进攻方向箭头：f0.attack_dir (+1 = 主队攻 +x)
}
```

## 6. 读取示例：SysModel（Python）

```python
import json, math
from pathlib import Path
root = Path('sample_25hz_10min')
meta = json.loads((root/'metadata.json').read_text())
hz = meta['frame_hz']
frames = [json.loads(l) for l in open(root/'tracking.jsonl')]
events = [json.loads(l) for l in open(root/'events.jsonl')]
team_of = {p['player_id']: p['team_id'] for p in meta['players']}

# 每个决策点 = 一个训练样本：(当前帧状态, 候选集合, 实际选择)
for e in (e for e in events if e['type'] == 'decision_point'):
    f = frames[round(e['available_at_ms'] * hz / 1000)]
    d = f['attack_dir'] if e['team_id'] == 'HOME' else -f['attack_dir']   # 统一成“向 +x 进攻”
    state = [(pid, x*d, y*d, vx*d, vy*d, math.atan2(math.sin(fa)*d, math.cos(fa)*d))
             for pid, x, y, vx, vy, fa in f['players']]
    options = [(o['type'], o['target_player_id'], o['success_prob'], o['xt_gain'], o['offside'])
               for o in e['options']]
    label = e['chosen_index']
```
注意：只能用 `available_at_ms ≤ 当前时刻` 的事件，避免泄露未来信息。

## 7. v0.1 的已知限制
- 只有一种阵型（4-3-3）。球员速度上限 7.2 m/s，偏低。球高度是抛物线，没有弹跳和空气阻力。
- 没有抢断、过人对抗、犯规和牌，pressure 也只是距离标签。
- 界外球、角球的开球点在场内 1.5 m 处（受球员靠近边线时的刹车模型限制）。
- 越位只在传球瞬间判定，不考虑"干扰比赛"等细节。
- 新生成的比赛在 `decision_point.policy` 写 `value_v1`（按选项价值选取，不再用 `heuristic_v0` 抽签）。xT 和 xG 仍是原来的解析公式。已入库的种子 8 切片保持 `heuristic_v0`。
