# 教练板数据 v1

免费演练就是这台生成器。训练行和教练当场看的片段用同一套输出：中圈原点、米、`decision_point`。工厂仍是 `touchline/scripts/synth/generate.py`（格式 0.1.0，生成器 `3.0.0-draft`）。不换神经网络来贴标签，也不把 Azure 额度花在造数据上。

联赛文件留在管线外面。`touchline/generate.py`（v2.1.0）写的是另一套回放：原点在左上角、y 向下、5 Hz、球员列没有面向、没有 `attack_dir`，`choose_action` 直接开球或开传，事件流里没有 `decision_point`，也没有带 `success_prob` 的候选列表。格式下限是 10 Hz，系统 1 按 FORMAT 第 6 节读中圈坐标。那 40 场北水联赛不能当作训练行，也不进演练。

## 1. 今天一帧和一个决策点怎么产生

一场从种子构造 `random.Random`。22 人的初值是同一套 4-3-3 模板 `BASE`：主队用模板坐标，客队 x 折成 `105 - x`。球在内部坐标 `(52.5, 34)`，也就是输出坐标的中圈。开球至少 12 秒，把球交给主队中锋（槽位 9）。

每一帧 `step` 做四件事：把模拟时钟设为 `frame / hz`；`move_players` 把 22 人朝各自目标挪一步；`update_ball` 按当前动作插值球；动作到期则 `finish_action`。带球结束才调用 `choose_action`。重新开球之后的第一下带球没有决策点（`decision=None`），带完才决策。

`choose_action` 先给本方 10 名场上球员各做一个传球选项（不含门将），门将以外的持球人再加一个带球和一个射门。每个选项当时就算好成功率、推进、xT、越位。然后用 `heuristic_v0` 抽一个，写成 `decision_point`：`available_at_ms` 等于随后那下动作的 `start_ms`。传球、带球、射门的结果要等动作走完才写入事件，读训练行的人只能用 `available_at_ms` 不晚于当前时刻的事件。

输出时内部坐标 `(x 从左向右 0..105，y 向下 0..68)` 换成中圈原点：`x_out = x - 52.5`，`y_out = 34 - y`，vy 取反。已入库样本 `sample_25hz_10min`（种子 8，25 Hz，10 分钟）有 15,001 帧、124 个 `decision_point`。

## 2. 哪些像球场，哪些会让教练不信

像球场的部分，都是代码里写死的几何，不是后加的解释：

- 场地 105 × 68，球门中心在两端，门宽 7.32 进了 xG 的张角。
- 上半场主队向 +x，下半场 `direction` 翻号，人走到另一头的目标，坐标不瞬移。半场 50 分钟（45+5），中场休息不模拟。
- 越位在传球瞬间判定：接球人在对方半场、比球更靠近对方球门、比对方倒数第二人更靠近对方球门。对方名单含门将，倒数第二人的取法和规则第 11 条的简化一致。
- 传球成功率沿传球线段量对方距离：`pass_prob = clamp(0.95 - risk - 0.006 * max(0, 长度 - 15), 0.05, 0.97)`，失败则多数被接球点附近的对方拿到，约 15% 沿出球方向飞出界。
- 界外球、角球、球门球、间接任意球、门将拿到球，都会把球交回最近的人再开。压力是 3 米、同一对人 6 秒冷却一次的距离标签。

会让教练不信的部分：

- 速度封顶：持球人 6.5 m/s，其余人 7.2 m/s，加速度上限 3.5 m/s²。持球人比追他的人慢，直线上追得上。7.2 m/s 低于比赛里的冲刺，FORMAT 第 7 节已写明偏低。人靠近边线会被刹车模型吸在内侧约 1.5 米，所以界外球和角球的开球点在场内 1.5 米，人走不到线上。
- 全场只有一套 4-3-3。无球目标是 `BASE` 槽位，再加 `0.35 * (球的推进 - 52.5)` 的整体推移，以及 x 方向 `1.4 * sin(...)`、y 方向 `1.5 * sin(...)` 的摆动。边锋、中锋、右边锋在本方控球且 `sin(t * 0.11 + index * 2.1) > 0.55` 时，目标 x 被拉到对方倒数第二人前方 1.5 米（再夹到 55..100）。这是节拍器插上，不是看传球时机的跑位。
- 没有对抗、犯规、牌。对方只有离持球人最近的两名场上球员去站到他侧前方 1.0 米和 2.4 米，球不会在带球过程中被碰掉。带球选项上的成功率 `clamp(0.95 - 0.12 * 五米内对方人数, 0.4, 0.95)` 只写进事件，`finish_action` 里带球一律成功。
- 射门结果不看 xG。选项上的 `success_prob` 是解析 xG，`start_shot` 却用固定权重抽 `goal / saved / off_target = 0.12 / 0.43 / 0.45`。射门落点的 y 在决策之后才随机，选项里的终点永远是球门中心。
- xT 和 xG 都是闭式公式，不是在比赛上拟合的转移矩阵。xT：`0.02 + 0.40 * exp(-到对方球门中心的距离 / 12)`，球门中心为 0.42。xG：张角和距离的 logistic，夹在 0.01 和 0.7。禁区里没有额外的平台。
- 选动作的是硬币，不是这些数。持球人不是门将、推进坐标 `> 78`（距对方球门线 27 米以内）且 `|y - 34| < 24` 时，以 0.06 的概率射门。否则以 0.36 的概率带球。剩下的质量在传球上按权重随机：偏好 17 米左右、推进有加成、乘上 `(0.5 + 成功率)`，越位只把权重打到 0.2 倍，并不剔除。`xt_gain` 不进入权重。门将没有带球和射门选项，也没有回传给门将的候选（循环从槽位 1 开始）。当前 softmax 模仿的就是这次抽取。`policy` 字段为 `heuristic_v0`。

## 3. v1 改动，按这个顺序

标签仍是「被选中的那个选项」。先让这个选项站得住，再让演练能画出那一下，再把量产和留出集分开。不另训一个网络来重贴标签。

**(a) 按价值选，去掉 0.36 / 0.06。** 候选怎么生成先不动（传球点仍是对方 0.25 秒外推，带球终点仍在前方 3–12 米、横向 ±7 米里随机）。变的是选择。越位传球不参与比较。公式以 `docs/coach-board-model.md` 的 `value_v1` 为准，不用丢球扣分：

```
传球、带球: value = success_prob * max(progress_m, 0)
射门:       value = success_prob * 20
```

20 米是写进事件的常数。xG 0.30 的射门价值为 6，与一次成功率 0.75、推进 8 米的传球相同。远射不再用到球门的距离抬高自己。取价值最大者。平手时 `success_prob` 更高者优先，再按 `option_id`。`policy` 写成 `value_v1`。短带球且 3 米内有对手，类别记为 `hold`。

紧接这一条、仍然算选择规则的收尾：带球结果改成服从该选项的 `success_prob`，失败就把球权交给 5 米内最近的对方球员，只有一次球权交换，没有身体对抗。射门是否进球改为以该选项的 xG 为概率，不进时再按现在的 0.43 : 0.45 拆成扑出和偏出。这样教练在片段里看到的频率，就是决策上写下的那个数。

**(b) 为鬼影路线补齐字段。** 每个选项已经有 `end_location` 和 `target_player_id`，但决策点上没有单独的路线，射门终点又总是球门中心，真正的射门 y 在 `start_shot` 里才抽。在 `decision_point` 上增加被选中的那一条：

```
route: {
  type,                  // pass | carry | shot
  target_player_id,      // 传球接球人；带球为 null；射门为 null
  end_location,          // 中圈原点，米
  direction_rad          // 输出坐标系里，从球指向 end_location
}
```

鬼影是决策时刻持球人到 `end_location` 的一段折线，不必存密采样。射门的 `end_location` 在做选项时就定在球门线上的一个点，`start_shot` 必须飞向同一个点。传球鬼影画的是选中的意图；被断之后球可以去别人脚下，鬼影不改写成断球路线。

**(c) 本机用不同种子多打几场。** 今天 `match_id` 写死 `SYN-SINGLE-0001`，命令行只有 `--hz --minutes --seed --output`。批量时每场的 `match_id` 必须带上种子，否则 20 个目录在索引里是同一场。种子用 1001–1020。输出放进已 gitignore 的 `touchline/scripts/synth/data/train/seed-<seed>/`。不要重新生成联赛，也不要覆盖 `sample_25hz_10min`（那是 `heuristic_v0` 的演示切片，种子 8，softmax 已经在上面拟合过）。

**(d) 两场留出，训练不许读。** 种子 9001 和 9002，`match_id` 为 `SYN-HOLDOUT-0001` 与 `SYN-HOLDOUT-0002`，目录 `touchline/scripts/synth/data/holdout/`。和训练场同样长度、同样 10 Hz、同样 `value_v1`。以后 `scripts/train_softmax.py` 见到这两个 `match_id`、这两个种子或这条路径就拒绝。种子 8 的切片不能充当留出集。训练里的射门少于 30、留出里的射门少于 15 时，用新种子继续加场，不加进留出目录。

这四条之后，只做两处让阵型站得住的事，见第 4 节：用教练给的 22 个点替换 `BASE`，并让无球目标锚在这些点上。解析 xT / xG 保持原公式。

v1 不模拟：犯规、黄牌、红牌；角球、任意球、界外球的套路（人墙、短角球、第二落点）。这些死球仍是现在的做法：球放到开球点，最近的人走过去，然后带球。也不做换人、疲劳、受伤、半场中途换阵，以及「干扰比赛」那类越位细节。

## 4. 教练的 22 个站位怎样成为演练初值

教练板给出 22 个点，坐标系与 FORMAT 第 1 节相同：中圈原点，x 沿长边，y 向上。每队 11 人，顺序固定为现在的 `POSITIONS`：GK，LB，LCB，RCB，RB，LCM，DM，RCM，LW，ST，RW。每点至少有 `team_id`、`player_id`、`x`、`y`。

写入模拟器内部坐标时用 `out_xy` 的逆变换，并夹到离界 0.5 米以内：

```
internal_x = x + 52.5
internal_y = 34 - y
```

客队的点已经在教练板上。不能再套 `__init__` 里那句 `105 - x`，否则客队会叠回主队半场。初速度为 0。上半场主队面向 0（+x），客队面向 π。

只改第 0 帧的坐标不够。`target_position` 每帧都读 `BASE[slot]`，几秒内人会走回那套 4-3-3。v1 把每个槽位的锚换成「本方进攻方向为 +x」的局部坐标：主队局部坐标就是内部坐标；客队 `local_x = 105 - internal_x`，`local_y` 不变。后面的 `direction == -1` 时再折回 `105 - x`，中场交换进攻方向时这套锚仍然可用。球的 0.35 倍推移和朝持球人靠拢的两名防守球员保留，摆动正弦可以留下，幅度仍是现在的 1.4 米和 1.5 米。`metadata` 里的阵型字符串在锚不是 `BASE` 时写成 `custom`。

球的默认值仍是中圈开球，主队中锋来开。教练若指定 `ball_owner_id`，球放在该球员脚下，控球记在他的队，动作为一次向前的短带球，其他 21 人留在给定的点上，不先排开球仪式。演练时长用现有的整分钟参数：`--minutes 1`。短于 100 分钟时 metadata 里 `clip` 已为 true。

## 5. 体量（笔记本，只跑 CPU）

已入库的 10 分钟、25 Hz、种子 8：124 个 `decision_point`，约 12.4 个/分钟。决策发生在带球结束，带球时长是 1.6–4.8 秒的均匀随机，所以降到 10 Hz 几乎不减少决策条数。10 Hz 是格式允许的下限。

本机实测一次：`python touchline/scripts/synth/generate.py --hz 10 --minutes 1 --seed 1`，墙钟 0.35 秒，601 帧，`tracking.jsonl` 702,119 字节（约 1.17 KB/帧），5 个决策点。第一分钟含至少 12 秒开球和两次死球，决策比稳态少。稳态按上面的 12.4 个/分钟估算。

| 用途 | 场次 | 每场 | 频率 | 种子 | 决策点（约） | 帧 | tracking |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 训练 | 20 | 20 分钟 | 10 Hz | 1001–1020 | 4,000–6,000，中心约 5,000 | 240,020 | 约 280 MB |
| 留出 | 2 | 20 分钟 | 10 Hz | 9001–9002 | 约 500 | 24,002 | 约 28 MB |
| 教练看的一次演练 | 1 | 1 分钟 | 25 Hz | 当次演练种子 | 开球分钟偏少，量级约 10 | 1,501 | 约 2 MB |

训练加留出是 420 个模拟分钟。按实测 0.35 秒/模拟分钟外推，大约两三分钟 CPU；加上 20 次进程启动和写盘，按 10 分钟预算。25 Hz 的一分钟演练帧数是 10 Hz 的 2.5 倍，按帧数比例大约 1 秒，这一档没有另测。不要为了加量去跑 25 Hz 的 100 分钟全场，也不要动联赛生成器。

## 6. Hugging Face

没有一个已经公开、能直接吐出 22 人跟踪加一条可防守决策的预训练模型，数据工厂仍用规则模拟器。仓库里的 [`martinjolif` 三个 YOLO](https://huggingface.co/martinjolif/yolo-football-player-detection) 只检测画面里的人、球和场地关键点，不产生比赛状态。TacticGen 在论文里同时生成球和 22 名球员的后续 5.4 秒，但作者仓库写明代码、权重和数据集都还没放出（[Jasonxu1225/TacticGen](https://github.com/Jasonxu1225/TacticGen)）。GenTac 是轨迹与事件的扩散模型论文页（[GenTac](https://huggingface.co/papers/2604.11786)），这次没有找到可下载的权重。`po03087/sra-trajectory-data` 里的扩散核只预报约 4 秒、23 个点的 xy，没有传球或射门决策（[数据集说明](https://huggingface.co/datasets/po03087/sra-trajectory-data)）。`cemrtkn/llm-football-simulator` 是 Mistral-7B 上的适配器，续写文字事件行，要 GPU，也不出 22 人坐标（[模型卡](https://huggingface.co/cemrtkn/llm-football-simulator)）。Google Research Football 是强化学习环境，不是按本格式落盘的数据工厂。这些都配不上「本机、无下载、标准库、价值标签」这条约束。不要把 100 美元 Azure 额度花在这里；叙述模型是另一条链路，不负责造跟踪。

Sources:

- [TacticGen 论文](https://arxiv.org/html/2604.18210)
- [TacticGen 仓库](https://github.com/Jasonxu1225/TacticGen)
- [GenTac 论文页](https://huggingface.co/papers/2604.11786)
- [sra-trajectory-data](https://huggingface.co/datasets/po03087/sra-trajectory-data)
- [cemrtkn/llm-football-simulator](https://huggingface.co/cemrtkn/llm-football-simulator)
- [martinjolif/yolo-football-player-detection](https://huggingface.co/martinjolif/yolo-football-player-detection)

## 7. 以后才会改的文件

现在一个都不改。

- `touchline/scripts/synth/generate.py`：`value_v1`、带球和射门与概率对齐、`route`、由种子生成 `match_id`、22 点锚、批量可调用的入口。
- `touchline/scripts/synth/FORMAT.md`：`route`、`policy: value_v1`、`formation: custom`。
- `touchline/scripts/synth/schema.json`：决策点上的 `route`，以及 `policy` 若被枚举则加上 `value_v1`。
- `touchline/scripts/synth/validate.py`：被选中的选项就是价值最大的那个；`route` 与该选项一致；射门飞行终点与 `route.end_location` 一致。
- `scripts/train_softmax.py`：读 `touchline/scripts/synth/data/train/` 下多场；拒绝 `SYN-HOLDOUT-0001`。
- `src/inside_the_game/features/from_tracking.py`：标签仍来自被选中的选项；鬼影折线可以从 `route` 读。
- `src/inside_the_game/system1/weights.json`：新标签生成之后再拟合。在那之前现有权重继续代表 `heuristic_v0`。
- `touchline/data/samples/README.md`：写明种子 8 的切片是旧策略演示，新训练行在 gitignore 的 `touchline/scripts/synth/data/`。
- 锁定旧决策计数或 `heuristic_v0` 的测试，主要是 `tests/test_from_tracking.py`。场景播放器用的 30 秒 `clip.jsonl` 在换切片之前保持不动。

不改 `touchline/generate.py`，不改 `touchline/data/league/`，不改 YOLO 权重路径，不在这条管线里调用 Foundry。
