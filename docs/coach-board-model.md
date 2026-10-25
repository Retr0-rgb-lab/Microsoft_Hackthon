# 教练板幽灵 v1：四类分布，再加一条路线

暂停在三维球场上的幽灵按 `ghost_simple` 交付两样东西。第一样是传球、射门、带球、停球四类的分布，四类都显示，概率最高的一类不叫最优。第二样是一条路线：传球接应人，或带球的方向和终点，或射门方向。传球弧线、贴地或过顶、射门技术是教练在这条直线上的批注，模型不预测。

本文只定这个模型。不改代码，不训练，不下载权重，不调用 Azure。

## 1. 现有模型相对 ghost_simple 的问题

核对结果如下。

`src/inside_the_game/system1/weights.json` 的 `fit_on` 是 `synthdata:SYN-SINGLE-0001:decision_point`，样本目录是 `touchline/data/samples/sample_25hz_10min`。`training.counts` 为 pass 73、dribble 41、hold 8、shoot 2，共 124 行。`scripts/train_softmax.py` 只读这场。没有留出场次。事件上的 `policy` 全是 `heuristic_v0`。这场 10 分钟里比分保持 `[0, 0]`。

六个特征是 `ball_x`、`ball_y`、`centrality`、`pressure`、`minute`、`goal_diff`。四类的 `goal_diff` 权重都是 `0.0`。拟合从 0 出发，这一列在样本里恒为 0，梯度就是 0，L2 也推不动它。`centrality` 由 `ball_y` 唯一决定。`pressure` 把最近对手的距离压进 0.18 到 0.82：3 米以内饱和为 0.82，12 米以外饱和为 0.18。`minute` 再除以 90，这场只走到第 10 分钟。

`fit_softmax` 打开了类权重。一类的权重是 `行数 / (4 × 该类行数)`。射门一行是 `124 / 8 = 15.5`，传球一行约 `0.42`。两条射门样本在拉射门这张平面。

标签规则写在 `weights.json` 的 `label_rule` 里，实现是 `label_decision_point`。选中的 pass、shot 记成 pass、shoot。选中的 carry 在 `progress_m < 4` 且最近对手不超过 3 米时记成 hold，否则记成 dribble。生成器没有 hold 选项，hold 是短带球的事后改名。

`touchline/scripts/synth/generate.py` 的 `choose_action` 这样抽签。守门员（`number == 1`）只进传球分支。其他人：推进 `progress0 > 78` 且 `|y − 34| < 24` 时，以 `0.06` 的概率选射门；否则以 `0.36` 的概率选带球；再不然在传球里按距离、向前推进、成功率和越位做加权随机。124 行标签模仿的是这次抽签。

分布不选路线。`decide_from_tracking` 同时给出 `primary_pass`、`secondary_pass` 和 `carry`。传球目标来自该决策选项里 `offside` 为假的传球，按 `completion.py` 的球权控制 × xT 排序。softmax 不参与。决策对象里没有射门方向。场面把传球线和带球线一起画上。`touchline/scene/src/panel.ts` 用 `topAction` 把概率最大的一类标成 `top`。

因此现有模型是：用一场合成数据上的位置特征，模仿一次 0.06 / 0.36 / 其余传球的抽签，再同时铺出传球和带球两条几何线。它没有一条幽灵路线，也没有一份只作为分布来读的四类概率。

## 2. v1 架构

只学习四类分布。路线仍用解析排序，不学习路线分数。

学习部分保持现在这一类模型：线性 softmax，全批量梯度，L2，标准库，本地 CPU。`weights.json` 这一次拟合就是这个量级。标签换成下一节的价值标签之后，几千行、八个特征、几百步，仍应落在秒到几分钟。超过几分钟就减步数或减特征，不换模型族。输出是四类概率，和为 1。权重文件里不写获胜类。

不学习候选路线上的分数。124 行里射门只有 2 行。路线模型要在每个决策的十余个候选里分出正样本，射门这条线没有可辨认的正样本。`completion_value` 已经在一次决策里对少数终点做解析打分，目标是 50 毫秒以内，而且不调用付费接口。

一条路线由解析分数选出，不由概率最高的类选出。

- 候选与标签用同一套资格：`offside` 为假的传球、带球选项、射门选项。守门员没有带球和射门时，候选只有传球。
- 传球终点和带球终点调用现成的 `completion_value`（球权控制 × 静态 xT）。路径是起点到终点的直线。带球的 `target_id` 仍是持球人。
- 射门不把球门中点送进球权控制。门将站在门口，控制权会把每一次射门压到末位。射门分等于该选项已有的 `success_prob`（生成器写出的 xG）乘以静态 xT 在球门中点的值，不再乘球权控制。按 `expected_threat` 的禁区公式，进攻坐标系下球门线中点（`x = 52.5`，`y = 0`）的 xT 是 `0.25 + 0.55 = 0.80`。xG 为 0.30 的射门得 0.24，xG 为 0.02 的射门得 0.016。这个 0.80 来自现有曲面，不单独训练。
- 三类候选放在同一个数列里取最大的一个，只画那一条。传球画到接应人，带球画到终点，射门画从球到球门方向的直线。
- 标签类是 hold 时不画线。分布里的 hold 份额照常显示。

分布回答「价值标签落在哪一类」。路线回答「声明过的解析分数下，哪一个选项排第一」。两样都显示。界面文案使用类别名和百分比，不使用最优、最佳、推荐决策。路线也不称为最优动作，它是这个声明分数的第一名。

## 3. 学习部分要用的特征

八个数值，全部来自 `available_at_ms` 那一帧和该决策自己的选项。坐标系保持中圈开球、米、105×68；先按 FORMAT 第 6 节把进攻方向翻到 +x，再归一。不读这一刻之后的传球、射门或带球事件。

| 特征 | 算法 |
| --- | --- |
| `ball_x` | 现有定义。本方球门线为 0，对方球门线为 1 |
| `ball_y` | 现有定义，范围 0 到 1 |
| `nearest_opponent_m` | 最近对手的米数，除以 30，截到 [0, 1] |
| `opponents_within_5m` | 5 米内的对手人数，除以 4，截到 [0, 1]。生成器的压迫计数用的就是 5 米 |
| `best_onside_pass_success` | 不越位传球中最大的 `success_prob`。没有则为 0 |
| `best_onside_pass_progress_m` | 这些传球中最大的 `progress_m`。负数记 0，除以 40，截到 [0, 1] |
| `carry_progress_m` | 带球选项的 `progress_m`。负数记 0，除以 20，截到 [0, 1]。没有带球则为 0 |
| `shot_xg` | 射门选项的 `success_prob`。没有射门则为 0 |

学习头去掉三列。`centrality` 是 `ball_y` 的函数。`minute` 覆盖的只是 90 分钟量程的前十分钟。`goal_diff` 在 `SYN-SINGLE-0001` 上恒为 0，六行权重都是 0；价值规则也不读比分。比分在样本里出现变化之前，这列留在权重文件外。

不加球员身份，不加 22 人的速度展开，不加图像特征。124 行辨认不了这些列。第 5 节的场次齐了以后仍用这八列；某一列若在留出对数损失上没有贡献，再删掉，不另加一列。

## 4. 数据组要打出的标签

`choose_action` 改为按价值选取。0.06 和 0.36 的抽签从选项目标里删除。每个 `decision_point` 写下表内的字段。训练只读这些字段。

资格与第 2 节相同：不越位的传球、带球、射门。

每个合格选项的价值：

- 传球和带球：`value = success_prob × max(progress_m, 0)`
- 射门：`value = success_prob × shot_gain_m`，其中 `shot_gain_m = 20`。不用射到球门中点的那一截推进米数。远射的米数会盖过禁区里的机会。20 是写进事件的常数，不是拟合结果。xG 0.30 的价值为 6，与一次成功率 0.75、推进 8 米的传球相同。

取价值最大的选项。平手时 `success_prob` 更高者优先，再按 `option_id` 字典序。选取过程不再调用随机数。

类别由这个胜出选项决定：

- 传球 → `pass`
- 射门 → `shoot`
- 带球，且 `progress_m < 4`，且该帧最近对手 ≤ 3 米 → `hold`
- 其余带球 → `dribble`
- 合格选项的价值全为 0 → `hold`，路线为空

事件至少包含：`policy`（固定写 `value_v1`）、`chosen_index`、`chosen_option_id`、`label_class`、`label_value`、`shot_gain_m`、`route_kind`（`pass`、`dribble`、`shoot`，hold 用空字符串）、`route_target_id`（传球为接应人，带球为持球人，射门和 hold 为空）、`route_end`（中圈坐标系下的终点；射门是球门方向上的点；hold 为空）。

弧线、传球 `height`、射门结果（进、扑、偏出）不写入标签。`policy` 仍为 `heuristic_v0` 的比赛，训练脚本应当拒绝，避免和旧的 124 行混在同一次拟合里。

## 5. 训练与留出

数据仍来自 `touchline/scripts/synth/generate.py` 的 v0.1 中圈开球生成器。联赛生成器不在范围内。先换上第 4 节的标签，再从 0 初始化重拟合。现有 `weights.json` 不作初值，也不在这 124 行上继续训练。

场次从 10 个种子起，每个种子仍是现在这种 10 分钟片段。8 场训练，2 场整场留出。留出单位是场。同一场进攻里的决策点彼此相关，从 `SYN-SINGLE-0001` 里拆行不算留出。

射门在现有一场里只有 2 次。训练场所含 `shoot` 少于 30、留出场所含少于 15 时，用同一生成器继续加种子。在达到这两个数之前可以拟合四类，但不向教练展示射门一格已经校准。`fit_softmax` 在缺类时会报错，所以每个划分里四类都要出现。

展示用概率来自不加权的拟合。类权重会把稀有类的份额从出现频率上抬高，教练看到的百分比会偏离场上的比例。现有文件的 `class_weighted: true` 只留作对照运行，不作为幽灵上的分布。L2 与全批量保持不变。

留出的整场上计算两个数。

1. 四类对数损失，用自然对数，逐决策等权。对照是训练集的类别频率向量，放在留出场上再算一次对数损失。过关线：留出对数损失 ≤ 0.65，并且比该频率对照至少低 0.20。现有 73 / 41 / 8 / 2 的频率熵约 0.92，0.20 的降幅要求模型用上这一帧的特征。不用准确率做门槛。传球约占六成时，永远预测传球也有约 0.59 的准确率。
2. 路线一致率：解析排序选中的 `option_id` 与 `chosen_option_id` 相同的比例。过关线 ≥ 0.70。十条冻结里至少七条，画出的那条路线就是价值标签选中的选项。

两条都过，才用这次拟合替换教练面前的幽灵。对数损失过了而路线低于 0.70 时，新拟合只显示四类份额，不画箭头。路线过了而对数损失未过时，这次拟合的分布和箭头都不展示。过关之前，板仍用已检入的 `weights.json` 离线显示，并标明这是未校准的预览，不把最大类叫成最优。

## 6. 标签若仍是 heuristic_v0

分布学到的是抽签。在射门区里，射门份额会停在 0.06 附近：xG 升高不会把它抬上去，眼前有更好的传球也不会把它降下来。带球份额会停在 0.36 附近（守门员除外），跟这脚带球的推进几乎无关。传球接应人之间的加权随机只改变路线，不改变类别，softmax 看不见接应人。

这种标签上，留出对数损失可以低于频率对照，幽灵仍然是错的。那只说明模型记住了硬币。球权控制 × xT 的箭头去对这枚硬币，路线一致率过不了 0.70。不要为了现有 124 行放低这条线。

`goal_diff` 继续是全 0。类权重会继续放大那两条射门。hold 继续是短带球的事后改名，表达不了「合格传球的价值都是 0，所以停住」。

## 7. 明确不做的事

- 不用 Azure GPU，不做托管微调，不下载足球预训练模型。本地能做的拟合留在 CPU 上。订阅额度不进入这条训练计划。仓库里已有的 Foundry 解说是另一条路径，本模型不依赖它。
- 不模仿 `heuristic_v0`。不把现有 `weights.json` 称为 v1。
- 不预测传球弧线、贴地或过顶、射门技术。这些是教练批注。
- 不把概率最高的一类叫最优。四类份额都显示。
- 不把解析路线叫最优动作。它是第 2 节那个分数的第一名。
- 不在 StatsBomb 上重拟合，不接联赛生成器，不把视频或图像特征送进这个 softmax。

## 8. 以后要动的最小代码路径

这次只列文件名。

标签在 `touchline/scripts/synth/generate.py`。

分布的特征和拟合：`src/inside_the_game/features/extract.py`，`src/inside_the_game/features/from_tracking.py`，`src/inside_the_game/features/from_cv.py`，`src/inside_the_game/system1/fit.py`，`src/inside_the_game/system1/policy.py`，`src/inside_the_game/system1/weights.json`，`scripts/train_softmax.py`。

一条路线在 `src/inside_the_game/system1/tracking.py`。它继续调用 `src/inside_the_game/system1/completion.py` 给传球终点和带球终点打分。射门分在 `tracking.py` 里按第 2 节计算，不把球门中点送进球权控制。

幽灵表面：`touchline/scene/src/decisions.ts`，`touchline/scene/src/overlay.ts`，`touchline/scene/src/panel.ts`。`topAction` 对最大类的高亮在这里去掉。

决策字典从 `primary_pass`、`secondary_pass`、`carry` 改成一条路线之后，下列调用方要跟着改键名：`src/inside_the_game/system1/orchestrator.py`，`src/inside_the_game/system1/agent_workflow.py`，`src/inside_the_game/system2/foundry.py`。
