# 教练板 v1

产品规格。模型、数据和前端按本文实现。本文没有写到的交互、对象和入口，不在 v1 里做。

名称与仓库对齐：

- 坐标系和文件用 `touchline/scripts/synth/FORMAT.md` 的 v0.1（中圈开球点、米、105×68、y 向上、`attack_dir`）。
- 类别模型用 `docs/v1-model-selection.md`：四类线性 softmax，`pass` / `shoot` / `dribble` / `hold`。权重文件是 `src/inside_the_game/system1/weights.json`。
- 路线排序用 `inside_the_game.system1.completion` 的 `pitch_control_x_xt`。
- 3D 与 2D 沿用 `touchline/scene` 的 broadcast 相机和 top-down 相机，以及那里的坐标映射：数据 `(x, y, z)` → three.js `Vector3(x, z, -y)`。
- 样本场是 `touchline/data/samples/sample_25hz_10min/`，`match_id` 为 `SYN-SINGLE-0001`。

## 1. 产品一句话

教练在一块可暂停的三维球场上亲手画传球、带球、射门和阵型，暂停时模型以淡色补上一个动作类别和一条路线，教练接受后它才变成墨迹；演练是规则模拟器按这块阵型生成的一段回放。

两处用途，同一块板：赛后给球员讲这一下，赛前把阵型摆好再生成一段演练。联赛浏览器不是这条产品的入口。

## 2. 一次使用

一次会话只有两种打开方式。

**赛后。** 教练打开一个 v0.1 目录（`metadata.json` + `tracking.jsonl`，可带 `events.jsonl`）。默认样本是上面的 25 Hz 片段。播放用该目录的 `frame_hz`。空格暂停，再按空格继续。暂停时播放头落在 `frame_id = round(t_ms * frame_hz / 1000)` 这一帧。

**赛前。** 教练打开一块空板。板上是 22 人，站位取 `touchline/scripts/synth/generate.py` 的 `BASE` 经 `out_xy` 换到中圈坐标：主队照此摆，客队以 `x → -x` 镜像。角色顺序与该文件的 `POSITIONS` 一致，`H01`–`H11`、`A01`–`A11`。默认 `attack_dir = +1`（主队攻 +x），比分 `[0, 0]`，`t_ms = 0`。这块板只有一帧，没有比赛进程。

两种打开方式之后，教练做的是同一组事：

1. **看。** 相机在「转播」（3D 透视，broadcast）和「俯视」（2D 上帝视角，top-down）之间切换。两台相机看同一批人、同一批墨迹、同一个鬼影。切换不改坐标。按钮文案用场景里的「转播」「俯视」；键 `1` / `b` 为转播，`2` / `t` 为俯视。默认转播。
2. **暂停。** 只有暂停时才出现鬼影和四类概率。播放中只显示人和已经画上的墨迹。
3. **画。** 任何时候都能画，包括模型给错的时候，包括没有鬼影的时候。画下去的就是墨迹，立刻是实线。
4. **接受。** 暂停时，`Tab` 或点在鬼影笔画上，把鬼影收成墨迹。`Esc` 把这一帧的鬼影收起，直到换帧。鬼影不自动变墨迹。
5. **改阵。** 进入「阵型」。赛后片段里的追踪球员不可拖；阵型是另一层 22 个槽位。赛前板上，这 22 人就是阵型，直接拖。拖动在两台相机里改的是同一组 `(x, y)`。
6. **演练。** 教练指定时长，默认 30 秒，用当前阵型生成一个新的 v0.1 目录，然后把这块板切去播放那个目录。演练是生成片段的回放。墨迹不驱动模拟。

赛后想把看到的站位拿去演练：在暂停帧上执行「用当前帧填入阵型」，把该帧 22 人的 `x, y, facing` 抄进槽位；角色仍取 `metadata.players[].position`。然后进入「阵型」再改，再生成。

持球人：赛后用该帧的 `ball_owner_id`。赛前或阵型层，点一名球员把球放到他脚下（`z = 0`，水平距离 ≤ 0.6 m，与 FORMAT 的持球约束一致）；再点同一人，球收回，`ball_owner_id` 为空。

## 3. v1 做这些，以后再做那些

### v1

- 墨迹四种：传球、带球、射门、停球标记。停球标记只在接受 `hold` 时写下。阵型编辑：22 个位置和角色。
- 鬼影：暂停帧上的四类概率，加**一条**淡色路线。`hold` 没有路线。
- 接受：`Tab` 或点击，把类别和那一条路线写成墨迹。弧线和动作技术不跟着写上。
- 相机：转播与俯视对切，映射与 `touchline/scene` 相同。
- 演练：改进后的 `touchline/scripts/synth/generate.py` 生成片段，可从教练编辑的阵型开球或开带。观看就是播放该片段。
- 板文件 `board.json`（见第 4 节）。墨迹写在板文件里，不回写 `tracking.jsonl` / `events.jsonl`。
- 类别模型这一轮要换训练标签：生成器按价值选动作，再在本机重拟合。输出仍是四类分布加一条路线，不把最大概率叫成最优。新权重到来之前，板必须能不联网、不调用 Azure，用已检入的 `weights.json` 跑起来。
- 选中一条墨迹后可改它的教练字段，`Delete` 删除，`Ctrl+Z` 撤销最近一次添加、接受或删除。

### 以后

- 更完整的球和人的物理：弹跳、空气阻力、变向刹车，以及把持球人 6.5 m/s、其他人 7.2 m/s 的速度上限和 `generate.py` 里的刹车距离一起改。v1 不动这些数。
- 抢断、对抗、犯规、牌，以及新的事件类型。
- 旁白。`docs/v1-model-selection.md` 里的 Azure AI Foundry、`gpt-4.1-mini`、`responses_narrator` 不进入教练板。
- 把 Azure 当作训练或运行的依赖。本机能做的都在本机做。
- 删除或替换 Touchline 联赛界面（`touchline/` 的 dashboard、`data/league/`）、`web/` 的 Scheme A 转播壳、`touchline/scene` 样本，以及 `fixtures/statsbomb/`。
- 用墨迹驱动演练（让模拟器按画下的箭头踢球）。
- 视频或 CV 作为模型输入。
- 导出成片、分享链接、球员账号、片段库和赛季浏览器。v1 只打开一个 v0.1 目录，并播放刚刚生成的那一次演练。
- softmax 预测接球人、弧线、传球高低、射门技术。
- 把公共模型放进板的运行时。

## 4. 对象和字段

坐标一律是中圈开球点、米。角度是弧度，`0` 朝 +x，逆时针为正，范围 `(-π, π]`，与 FORMAT 的 `facing` 相同。`team_id` 只有 `HOME` 和 `AWAY`。

### 帧

赛后帧就是 v0.1 `tracking.jsonl` 的一行。板要读的字段：`frame_id`、`t_ms`、`period`、`attack_dir`、`in_play`、`phase`、`possession_team_id`、`ball_owner_id`、`score`、`players`（22 × `[player_id, x, y, vx, vy, facing]`）、`ball`（`[x, y, z, vx, vy, vz]`）。

赛前和阵型层合成一帧，字段同上：`frame_id = 0`，`t_ms = 0`，`period = 1`，`in_play` 在已指定持球人时为 `true`、否则为 `false`，`phase` 在有持球人时为 `carry`、否则为 `restart_setup`，速度全 0，`ball.z = 0`。

拒绝 `coordinate_system.origin` 不是 `centre_spot`，或场地不是 105×68 的目录。`touchline/generate.py`（左上角原点、5 Hz 的联赛生成器）不进入板，也不进入模型。

### 板文件 `board.json`

| 字段 | 含义 |
|---|---|
| `schema` | 固定 `"coach-board/1"` |
| `source` | `"clip"` 或 `"setup"` |
| `clip_dir` | 赛后片段或演练产物的目录；赛前未演练时为 `null` |
| `camera` | `"broadcast"` 或 `"top"` |
| `formation` | 下面的阵型对象 |
| `ink` | 墨迹数组 |

鬼影不写入文件。它由暂停帧和当前权重算出来。

### 阵型

| 字段 | 含义 |
|---|---|
| `label` | 教练写的短名称，默认 `"4-3-3"`。只是标签，不解析成站位 |
| `attack_dir` | `+1` 或 `-1`，含义同 FORMAT：主队是否攻 +x |
| `slots` | 长度 22 |

每个槽位：`player_id`、`team_id`、`role`、`x`、`y`、`facing`。

`role` 只允许 `generate.py` 已有的 11 个：`GK`、`LB`、`LCB`、`RCB`、`RB`、`LCM`、`DM`、`RCM`、`LW`、`ST`、`RW`。换阵型是改坐标，不是发明新角色字符串，也不是输入 `"3-5-2"` 自动落位。`x` 在 `[-52.5, 52.5]`，`y` 在 `[-34, 34]`。v1 不增减人，不设替补。

### 传球墨迹

| 字段 | 含义 |
|---|---|
| `ink_id` | 板内唯一 |
| `kind` | `"pass"` |
| `frame_id`、`t_ms` | 画下或接受时的帧 |
| `team_id` | 出球人的队 |
| `from_player_id`、`to_player_id` | 球员 A 到球员 B，都必填 |
| `start`、`end` | `[x, y]`，接受时取该帧两人的位置 |
| `path` | 折线。直线是 `[start, end]`。弧线是二次贝塞尔上的 9 个点（起、7 个采样、终） |
| `style` | `"ground"` 或 `"loft"`。教练字段。接受鬼影时写成 `"ground"` |
| `curve` | `"straight"` 或 `"curved"`。接受鬼影时写成 `"straight"` |
| `control` | 弧线的一个控制点 `[x, y]`；直线时为 `null` |
| `source` | `"coach"` 或 `"ghost_commit"` |
| `visible_ms` | 默认 `4000` |

画法：点 A，再点 B。然后可以改 `style`，或把 `curve` 设为 `curved` 并拖出一个控制点。模型不填 `style` 和 `curve`。

`style` 与生成器事件字段的对应，仅在以后要把墨迹交回模拟器时使用：`ground` → `pass_height: ground`，`loft` → `pass_height: high`。v1 演练不读墨迹。

### 带球墨迹

| 字段 | 含义 |
|---|---|
| `kind` | `"carry"` |
| `from_player_id` | 持球人 |
| `start`、`end` | `[x, y]`。`end` 是教练点的落点，或鬼影路线的终点 |
| `path` | 起终点之间的直线折线 |
| `direction_rad` | 由 `start → end` 得到，约定同 `facing` |
| `source`、`frame_id`、`t_ms`、`team_id`、`visible_ms` | 同传球 |

没有 `style`，没有 `curve`。画法：点持球人，再点场地落点。softmax 的 `dribble` 接受后写成 `carry`。

### 射门墨迹

| 字段 | 含义 |
|---|---|
| `kind` | `"shot"` |
| `from_player_id` | 射门人 |
| `start`、`end` | `[x, y]`。`end` 是地面瞄准点 |
| `path` | `[start, end]` |
| `direction_rad` | 箭头方位，由 `start → end` 得到 |
| `angle_rad` | 与 `direction_rad` 同一几何：改角度就绕射门人旋转 `end`，长度不变；拖 `end` 就回写角度 |
| `style` | `"unset"`、`"driven"`、`"placed"`、`"chip"`。接受鬼影时写成 `"unset"`，由教练再选 |
| `source` 及时间字段 | 同传球 |

画法：点射门人，再点瞄准点。`style` 不改变 `path`。softmax 的 `shoot` 接受后写成 `shot`。

### 停球墨迹

`kind` 为 `"hold"`。字段：`ink_id`、`frame_id`、`t_ms`、`team_id`、`player_id`、`at`（`[x, y]`，该帧持球人脚下）、`source`、`visible_ms`。没有 `path`。只由接受 `hold` 鬼影产生；教练不从工具栏另画一种箭头。

### 墨迹何时可见

播放头在 `[t_ms, t_ms + visible_ms]` 内时显示。暂停在它的 `frame_id` 上时保持显示。这不是 `touchline/scene` 决策叠层的 8 秒规则；那条规则只属于场景样本里的 `decisions.json`，教练板不读 `decisions.json`。

### 鬼影

暂停且该帧 `ball_owner_id` 非空时计算一次。球在空中、死球、没有持球人：不显示鬼影。守门员的判定用槽位或 metadata 的 `role == GK`，不用球衣号码硬编码。

| 字段 | 含义 |
|---|---|
| `frame_id`、`t_ms`、`player_id`、`team_id` | 持球人和他的队 |
| `probabilities` | `pass`、`shoot`、`dribble`、`hold`，和为 1，顺序与 `weights.json` 的 `labels` 一致 |
| `suggested_class` | 概率最大的一类。并列时按 `pass`、`shoot`、`dribble`、`hold` 取先出现的，与 `touchline/scene/src/decisions.ts` 的 `topAction` 相同 |
| `route` | 下面的一条路线，或 `null` |
| `score_method` | 有路线时固定 `"pitch_control_x_xt"` |
| `weights_version`、`fit_on` | 抄自当前权重文件，供界面脚注 |

`route`：`kind`（`pass` / `carry` / `shot`）、`target_id`、`path`、`end`、`score`。

- `suggested_class == pass`：`kind = pass`，`target_id` 是接球人，`path` 是两点线段。
- `dribble`：`kind = carry`，`target_id` 是持球人自己（与 `PitchPath` 的带球约定相同），`path` 为 5 点直线（`CARRY_STEPS`）。
- `shoot`：`kind = shot`，`target_id` 是射门人，`path` 是两点。
- `hold`：`route = null`。

该类别没有合法路线时，`route = null`，只显示概率和类别名，不画箭头。

绘制：鬼影透明度 0.35，墨迹不透明。鬼影只有一条路线。不画第二传，不用场景叠层那套「实线主传、半透明次传、虚线带球」。概率面板同时可见：四个数、`suggested_class`、以及路线的 `score`。这三个数不乘成一个分数。

界面文案把 `suggested_class` 叫「建议」。禁止出现「最优」「optimal」「best action」。概率面板旁固定一句：「类别来自启发式标签上拟合的 softmax，不是最优决策。」

### 类别与路线从哪一帧来

六个特征与 `features_from_tracking` 相同：`ball_x`、`ball_y`、`centrality`、`pressure`、`minute`、`goal_diff`。作用人是 `ball_owner_id`，队伍是他的 `team_id`，`minute` 来自 `t_ms`，比分来自帧上的 `score`。这一行只在内存里，不写入 `events.jsonl`。

路线的候选，按下面的优先顺序，只取一组：

1. 若 `events.jsonl` 里存在 `decision_point`，其 `available_at_ms` 等于该帧 `t_ms`，且 `player_id` 等于持球人：用 `decide_from_tracking`。传的候选是该事件里 `offside: false` 的传球，按完成分排序，鬼影只用第一名（`primary_pass`）。带球用该事件的 carry 终点；没有则用下面的 6 米兜底。射门用该事件 shot 选项的 `end_location`。
2. 否则从帧现算，不用随机数：
   - **传：** 其余本队球员的当前 `(x, y)`。越位检验用 FORMAT 第 4 节的简化第 11 条（对方半场、比球更靠近对方球门、比对方倒数第二人更靠近对方球门），越位的去掉。完成分最高的一个。同分时 `target_id` 字典序较小者优先，与 `tracking.py` 的排序一致。
   - **带：** 沿该队进攻方向 6.0 米，横向 0（`FALLBACK_CARRY_M`），夹紧在场地内。不用 `heuristic_v0` 里 3–12 米、横向 ±7 米的随机终点。
   - **射：** 被攻击球门的中心 `(52.5 * d, 0)`，`d` 是 FORMAT 第 6 节的进攻翻转（该队攻 +x 时 `d = +1`）。`role == GK` 时不产生射门候选，也不产生带球候选，与 `choose_action` 对 1 号的跳过一致。

`suggested_class` 决定画哪一条。传的完成分排名不改 softmax，softmax 也不选接球人。

## 5. 「合理」指什么

一次建议是一组分布加上一条按完成分排出的路线。

- **分布**回答「这一下更像传、射、带还是停」。它是四类 softmax。当前 `weights.json` 拟合于 `SYN-SINGLE-0001` 的 124 个 `decision_point`，一场 10 分钟、比分 0-0。标签来自 `heuristic_v0`：禁区附近约 6% 随机射门，约 36% 随机带球，其余是加权随机传球。特征只有上述六个标量。`goal_diff` 的权重在该文件里是 0。把最大概率叫成最优决策，与这次拟合不符。
- **一条路线**回答「若走建议的那一类，几何上落在哪」。传是一名接球人，带是一个方向，射是一个瞄准方向。排序键只有 `pitch_control_x_xt`（控制权是 σ = 7 m 的高斯影响份额，xT 是攻方坐标系上的静态曲面，二者都在 `completion.py`，都不是在真实比赛上拟合的转移矩阵）。完成分不是胜率，也不和概率相乘。
- **技术**不在建议里。地面或过顶、直线或弧线、射门的 `driven` / `placed` / `chip`，只存在于教练墨迹。

教练可以不接受。不接受时板上什么都不改。接受只复制类别和路线，`style` 与 `curve` 用第 4 节的默认值。

重拟合之后仍然输出分布，不把最大概率叫成最优。训练行只来自我们自己的 v0.1 合成 `decision_point`。标签改为生成器按价值选中的那一项，价值定义以 `docs/coach-board-model.md` 的 `value_v1` 为准，不再模仿 `heuristic_v0` 里大约 36% 带球、6% 射门的抽签。类别映射可以保留：传→`pass`，射→`shoot`，有推进或无人逼抢的带球→`dribble`，短带且 3 米内有对手→`hold`。不把 StatsBomb、联赛生成器或付费接口读进权重。

## 6. 相对原清单增加的决定

这些已经写进第 3–5 节，这里只说明原因。

- **墨迹单独落在 `board.json`。** 接受鬼影若去改 `events.jsonl`，会把 `heuristic_v0` 的标签改掉，样本就不能再当作同一次生成。
- **鬼影只在暂停、只对持球人、只画一条。** 原话是暂停后补全；场景叠层的主传加次传加带球是另一套演示，放进来会变成三条建议。
- **`hold` 写成无箭头的标记。** 四类里有停，接受时必须有对象可写。
- **没有 `decision_point` 的帧也给鬼影。** 教练会停在任意帧和赛前板上；只绑定那 124 个事件，赛前板没有建议。候选用第 4 节的确定性规则，避免各端自己抽样。
- **传的终点落在该帧球员脚下，带的兜底是直线 6 米，射的兜底是球门中心。** 生成器里的随机落点和随机射门纵向是标签噪声，不能当作建议。
- **越位传球不进入那一条路线。** `decide_from_tracking` 已经丢掉 `offside: true`。
- **阵型名称不解析，角色闭集为现有 11 个。** 否则前端会做一套阵型语法，生成器却只认识坐标和 `POSITIONS`。
- **赛后追踪不可拖，阵型是单独一层，并有「用当前帧填入阵型」。** 直接拖片段里的人会改历史帧；两个用途需要一条明确的拷贝。
- **演练不执行墨迹。** 原话是生成片段、可从编辑后的阵型开始。让箭头变成脚本是另一种策略。
- **演练在已指定持球人时从他脚下的 `carry` 开始，否则仍用现有开球，但 22 人的初始坐标换成阵型。** 这样「从这块阵型打一段」成立，又不用新写死球规则。
- **v1 不改 6.5 / 7.2 的速度上限。** 它和 `generate.py` 里的刹车距离绑在一起，只改上限会让出界和转身失真。动作更像球，留到和刹车、弹跳一起做。
- **概率、建议类别、完成分三者不合成一个数。** 合成之后界面上就会只剩一个「最好的动作」。
- **删除和一步撤销。** 不规定的话，各端会自己做一套历史。

数据侧若评估公共预训练模型：只有它能产出 v0.1 中圈坐标、105×68、带 `attack_dir` 的追踪或 `decision_point` 时，才可以用来**生产训练片段**。它不替换 `generate.py`，不进教练板进程，也不是 v1 的完工条件。对不上格式就不用。

## 7. 非目标

- 把最大概率或完成分最高的路线称为最优决策。
- 用 softmax 选择接球人，或让模型输出弧线、传球高低、射门技术。
- 用神经网络在演练里踢球。演练的执行者是 `touchline/scripts/synth/generate.py` 的规则模拟。新生成的场次把 `policy` 写成 `value_v1`。种子 8 的旧切片保持 `heuristic_v0`，不拿去重拟合。
- 把 `touchline/generate.py` 的联赛坐标或 `fixtures/statsbomb/` 放进模型或板。
- 以 Azure、Foundry 旁白、视频理解作为教练板的依赖。
- 在这一轮删除联赛界面、`web/` 转播演示或 StatsBomb 夹具。
- 富物理、犯规牌、按墨迹回放、成片导出、多用户。

## 8. 四份计划对齐之后的实现顺序

模型、数据、前端的说明分别在 `docs/coach-board-model.md`、`docs/coach-board-data.md`、`docs/coach-board-frontend.md`。下面这几条覆盖它们互相不一致的地方。

- 价值公式只用模型说明里的 `value_v1`：传球和带球是 `success_prob × max(progress_m, 0)`，射门是 `success_prob × 20`。不另加丢球扣 12 米，射门也不乘 35。
- 训练 20 场、每场 20 分钟、10 Hz，种子 1001–1020。留出 2 场，种子 9001 和 9002，训练脚本拒绝这两场。射门在训练里少于 30、留出里少于 15 时继续加种子。不覆盖 `sample_25hz_10min`。教练演练仍是 25 Hz、默认 30 秒，可以从阵型开球。
- 阵型是单独一层。赛后片段里的人不能拖。要演练时先「用当前帧填入阵型」。无球跑位的锚必须换成这 22 个点，否则人会走回 4-3-3。
- 接受 `hold` 写下无箭头的停球标记。传球方式只有 `ground` 和 `loft`，弧线只有 `straight` 和 `curved`。射门方式是 `unset`、`driven`、`placed`、`chip`。前端说明里的 `lofted`、`driven` 传球和内弧外弧不采用。
- 没有 `decision_point` 的暂停帧仍给一条确定性鬼影（产品第 4 节）。训练行只来自 `decision_point`。

实现按这个顺序，前一步没有可看的产物就不做下一步：

1. 生成器改为 `value_v1`，写上路线字段，阵型能当锚。本地打一场几分钟的样本，确认被选中的选项就是价值最大的那个。
2. 按模型说明改特征和训练脚本，在本机拟合。留出对数损失和路线一致率没过关，板上继续用已检入权重，并标明未校准。
3. 新建 `touchline/board/`，端口 5175。先只播放片段，转播和俯视能切换。
4. 暂停时画出四类概率和一条淡色路线，`Tab` 或点击收成墨迹。
5. 手画、阵型层、从阵型生成一段演练并播出来。浏览器里不跑生成器，演练由本机 Python 事先写好。
