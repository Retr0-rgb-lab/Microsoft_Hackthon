# 教练板前端 v1

设计说明。这一版只定界面和数据，不改现有页面，也不接后端。

联赛界面留在 `touchline/index.html` 与 `touchline/app.js`，端口 5173。三维样本留在 `touchline/scene`，端口 5174。教练板是第三块画面：同一块球场上完成观看、标注和摆阵型。

球场用 v0.1 样本的中圈原点、米、105×68。数据 `(x, y, z)` 进 three.js 为 `(x, z, -y)`，`rotation.y` 用数据朝向。不读联赛那套左上角原点、5 Hz 的追踪。

## 1. 目录、端口、从 scene 拿什么

目录用 `touchline/board/`。它和 `touchline/scene`、`touchline/data/samples/sample_25hz_10min` 并列，样本相对路径好接，又不会变成联赛壳。

开发服务器 `127.0.0.1:5175`，`strictPort: true`。5173 和 5174 被占用时，本应用直接失败，不去抢端口。

Vite 别名 `@scene` 指向 `touchline/scene/src`。只读引用，不改 scene 里的文件。

直接引用：

| 模块 | 用途 |
| --- | --- |
| `coords.ts` | `PITCH`、`toScene`、`Frame`、`sampleAt`、`pose`、`facingDirection` |
| `pitch.ts` | `createStage`，草地和线 |
| `actors.ts` | 22 个胶囊、球、`applyPose` |
| `colors.ts` | HOME / AWAY 平色 |
| `decisions.ts` | `Decision`、`probabilities`、`primary_pass`、`carry`、`loadDecisions`、`decisionAt`、`topAction` |
| `hud.ts` | 时钟文案、片段文件名校验 |

`vite.config.ts` 里 `/sample` 指向同一样本目录的做法照抄一份到 board 自己的配置。默认片段仍是 `clip.jsonl`（25 Hz，约 30 秒）。`decisions.json` 放在 `touchline/board/public/decisions.json`，内容就是 `python scripts/export_decisions.py` 写出的那份决策核输出。

不引用 `main.ts`。那是固定相机、只靠 `requestAnimationFrame` 走时的样本壳。

不引用 `overlay.ts` 和 `panel.ts`。色带的画法留在 board 里新写 `ink.ts`：贴地扁带、箭头、传球黄 `0xffe500`、带球青 `0x3ad6ff`。scene 的 overlay 只认识决策对象，会按 `event_id` 整组换掉，也没有射门，没有教练字段。

## 2. 一块屏幕

整页一块画布，球场铺满。上面叠四件控件，都在同一页里切换，不另开应用。

**工具轨**在左侧，四选一：传球、带球、射门、阵型。前三个是标注模式。阵型是摆人模式。播放中工具轨还在，但射线拾取关掉。

**幽灵层**是球场上的一条淡色路线，加一枚小标签（动作类和该类概率）。只在暂停、并且当前时刻能对上一条决策时出现。

**相机**在右上，两个按钮，文案沿用 scene：转播、俯视。快捷键 `1` / `b`，`2` / `t`。转播是现有的透视相机（视角 28°，位置约 `(-6, 9.5, 46)`，看向 `(14, 1.2, 0)`）。俯视是现有的正交相机，从上方盖住 105×68。

环绕只为摆阵型。进入阵型模式时，把 `OrbitControls` 挂到转播那台透视相机上，目标在中圈，极角限制在草皮之上。俯视时卸掉环绕：上帝视角配地面射线就够拖人。离开阵型模式时卸掉控件，回到进入前的转播或俯视。标注和演练不用第三台相机。

**运输条**在底部：播放、暂停、时间条。空格切换暂停，与 scene 相同。时间条按 `t_ms` 拖，松手停在该帧，画面用 `sampleAt` 在相邻帧之间插值。演练放到片段末尾就暂停，不循环。

三种用法是模式：

- 演练：运输条播已经载入的片段。胶囊跟着片段走，页面不控制人。
- 标注：暂停。传球、带球、射门往墨迹列表里写。
- 阵型：暂停。拖胶囊改 `x, y`。

播放时标注和拖拽都停用。已经写下的墨迹留在场上，跟着世界坐标，不跟着某一帧消失。

## 3. 每个工具怎么用

拾取用射线。点胶囊选人，点草皮选地面点。scene 里没有这层，board 自己加。

坐标一律写回中圈米制。画的时候走 `toScene`。

### 传球

选中传球，播放暂停。

先点球员 A，脚下出环。再点球员 B。A 到 B 立刻成为已提交墨迹：实色黄带加实心箭头。

然后教练补两个字段，模型不出这两个：

- 方式 `style`：`ground` 地面、`lofted` 高空、`driven` 低平。地面贴着草；高空把带在 three.js 的 Y 上拱起，平面落点仍是 A、B；低平比地面略宽。
- 弧线 `curve`：`straight` 直线、`inside` 内弧、`outside` 外弧。内弧把中点向路径左侧偏 4 米，外弧向右侧偏 4 米。这是粉笔弯度，不是球的物理。

### 带球

选中带球，播放暂停。

点持球人，在草皮上拖出方向，松手写成墨迹。几何上是两点箭头。颜色用带球青，保留 scene 的虚线（实段 1.7 米、空段 1.0 米），并加上实心箭头。scene 的带球带没有箭头，教练板需要方向。

没有方式和弧线。

### 射门

选中射门，播放暂停。

点射门人，在草皮上拖出方向，松手写成墨迹。颜色 `0xff8a3d`，实色带加实心箭头，和黄、青分开。

角度 `angle_deg` 由页面算：从该球员指向球门中点 `(attack_dir × 52.5, 0)` 的射线，到所画箭头的有符号夹角，正方向朝数据 +y。`attack_dir` 用这一帧的值，+1 表示 HOME 攻 +x。

方式 `style` 是教练字段：`placed` 推射、`driven` 抽射、`chip` 挑射。未选时为 `null`。

### 阵型

选中阵型，播放暂停，透视相机加上环绕。

拖胶囊，射线落在草皮上，改该人的 `x, y`。v1 不改 `facing`，也不拖球。22 人都可以动。

拖完的姿态留在内存，字段仍是 `player_id`、`team_id`、`x`、`y`、`facing`。它不写回正在播的 jsonl。再按播放时，画面回到已载入片段里的位置；回到阵型模式时，再套上内存里的工作姿态。

演练只播放已经生成好的片段。片段可以是样本，也可以是生成器从这份姿态起头之后写出的新 jsonl。页面提供载入片段。页面不生成片段，也不在播放时替人做决策。

### 幽灵

暂停时出现，语义和 Cursor 补全一样：建议，还不是墨迹。

用 `topAction(probabilities)` 取一类。标签与模型一致：`pass`、`shoot`、`dribble`、`hold`。界面把 `dribble` 说成带球，把 `shoot` 说成射门。平局时的取舍与 `decisions.ts` 相同：只有严格更大才替换，顺序是 pass、shoot、dribble、hold。

只画一条路线：

| 动作 | 路线从哪来 |
| --- | --- |
| `pass` | 只用 `primary_pass`（`target_id`、`path`、`score`）。不画 `secondary_pass`。 |
| `dribble` | 用 `carry.path`，画成方向。 |
| `shoot` | 决策对象没有射门路径。从 `player_id` 的当前位置连一条直线到球门中点 `(attack_dir × 52.5, 0)`，并标 `derived: true`。 |
| `hold` | 只有标签，没有路线。 |

不幽灵弧线，不幽灵射门方式。传球幽灵也不带 `style` 和 `curve`。

接受：暂停且这条幽灵有路线时，按 `Tab`，或点那条淡色带。`Esc` 丢掉当前幽灵，直到 `t_ms` 再变。`hold` 按 `Tab` 不写墨迹。

接受之后写一条墨迹，然后藏起幽灵，直到时刻变化。

- 传球：`from_id` 用决策的 `player_id`，`to_id` 和 `path` 用 `primary_pass`。`style` 先写成 `ground`，`curve` 先写成 `straight`，教练可以再改。
- 带球：`path` 用 `carry.path`。
- 射门：`path` 用那条推导直线，`angle_deg` 按上面的夹角写上，`style` 保持 `null`，等教练选。

外观和已提交墨迹分开：

- 幽灵：不透明度约 0.28，一律虚线，空心箭头，颜色发灰，标签上是动作名和该类概率（例如 `shoot 31%`）。
- 墨迹：不透明度约 0.95。传球实线加实心箭头，带球虚线加实心箭头，射门实线加实心箭头。方式和弧线只体现在墨迹上。

播放时不显示幽灵。已提交墨迹保留。暂停时选决策不用 scene 的 8 秒上限：教练停在这一帧，就看这一帧能对上的最近一条。调用 `decisionAt(set, tMs, Number.POSITIVE_INFINITY)`。播放中既然不画幽灵，8 秒规则在这块板上用不到。

## 4. 暂停一帧要的数据

下面这份是页面停在某一帧时手里的文档。球员和球来自片段插值后的姿态；幽灵来自静态 `decisions.json` 里对上的那条 `Decision`；墨迹来自本页会话。

名字尽量沿用决策核已经在发的字段：`probabilities`、`primary_pass`、`carry`，以及 `target_id`、`path`、`score`。`dribble` 不要改名为 carry 再放进概率里。概率四键就是 `pass`、`shoot`、`dribble`、`hold`。

```json
{
  "schema": "coach-frame/1",
  "origin": "centre_spot",
  "pitch_m": { "length": 105, "width": 68 },
  "t_ms": 14360,
  "frame_id": 359,
  "attack_dir": 1,
  "pose_source": "clip",
  "players": [
    { "player_id": "H10", "team_id": "HOME", "x": 8.556, "y": 3.839, "facing": 1.2 }
  ],
  "ball": { "x": 8.5, "y": 3.7, "z": 0.2 },
  "ghost": {
    "event_id": "e000005",
    "t_ms": 14360,
    "frame_id": 359,
    "team_id": "HOME",
    "player_id": "H10",
    "probabilities": {
      "pass": 0.218,
      "shoot": 0.311,
      "dribble": 0.216,
      "hold": 0.254
    },
    "action": "shoot",
    "primary_pass": null,
    "carry": null,
    "shot": {
      "derived": true,
      "path": [[8.556, 3.839], [52.5, 0.0]]
    }
  },
  "ink": [
    {
      "id": "ink-1",
      "tool": "pass",
      "from_id": "H10",
      "to_id": "H09",
      "path": [[8.556, 3.839], [18.229, 23.11]],
      "style": "ground",
      "curve": "straight",
      "source": "ghost"
    },
    {
      "id": "ink-2",
      "tool": "carry",
      "from_id": "H10",
      "path": [[8.556, 3.839], [17.899, 9.646]],
      "source": "coach"
    },
    {
      "id": "ink-3",
      "tool": "shot",
      "from_id": "H10",
      "path": [[8.556, 3.839], [40.0, 2.0]],
      "angle_deg": 12.4,
      "style": null,
      "source": "coach"
    }
  ]
}
```

`players` 在文档里写全 22 人。上例只留了一个人。`x, y` 是中圈米，`facing` 为弧度，0 朝 +x。片段行里的 `vx, vy` 这一帧的画面用不到，v1 不放进这份文档。

`pose_source` 为 `clip` 时，人的位置来自片段。阵型拖过之后改为 `formation`。

`ghost.action` 用模型标签。`pass` 时填 `primary_pass`，形状与决策核相同：`{ "target_id", "path", "score" }`。`dribble` 时填 `carry`，同样三个字段，`target_id` 通常是持球人自己。`shoot` 时只填 `shot`，并且 `derived` 为 true。`hold` 时三条路线都是 null。

`path` 是 `[[x, y], ...]`，单位米，与 `public/decisions.json` 里的路径相同。

`ink[].source` 为 `ghost` 或 `coach`，方便以后看出哪一笔是接受补全、哪一笔是手画。`style` 和 `curve` 只出现在教练能设的笔上。射门的 `style` 可以是 null。

v1 幽灵的来源是静态文件：`loadDecisions("/decisions.json")`，集合形状就是现有的 `DecisionSet`（`schema_version`、`match_id`、`frame_hz`、`origin`、`decision_count`、`decisions`）。

以后的接缝：换成一次本地 Python 调用。请求体是这一帧的 `players`、`ball`、`t_ms`、`attack_dir`。响应仍是一条 `Decision`（`probabilities`、`primary_pass`、`secondary_pass`、`carry`）。页面只换加载函数。在决策核写出射门路径之前，射门幽灵继续由球门中点推导。这一步不需要 Azure。静态文件仍然可以当离线后备。

## 5. 现有 scene 不够的地方

`touchline/scene` 能播样本、能换两台固定相机、能把决策画成粉笔。教练板还要这些它没有的东西：

- 没有射线。点不到人，也点不到草皮。
- 没有拖拽。`applyPose` 每帧用片段盖住胶囊位置。
- 没有时间条。时刻只在 `requestAnimationFrame` 里往前走，或用地址栏 `?t=` 起播。空格只能暂停。
- 相机是写死的两台。没有环绕。
- `decisions.json` 启动时取一次，不会按当前姿态重算。
- `decisionAt` 默认超过 8 秒就返回 null，overlay 把画面清掉。暂停在一帧上研究时，这条规则会把建议弄没。
- overlay 只画 `primary_pass`、`secondary_pass` 和虚线 `carry`，没有射门，没有方式，没有弧线，也没有“淡建议 / 实墨迹”两层。

样本壳继续承担原来的演示。这些缺口在 `touchline/board` 里补，不回头改 scene。

## 6. 建造顺序

第一步先做能看的。搭 `touchline/board`，端口 5175，引用球场、胶囊和坐标，播 `clip.jsonl`。转播和俯视能换。运输条能播放、暂停、拖动。没有墨迹，没有阵型。看到 22 个胶囊和球，并且 5173、5174 仍归原来的两个应用，这一步就完成。

第二步做暂停幽灵。载入静态 `decisions.json`。暂停时画出一类动作和一条路线。`Tab` 或点击写成墨迹，播放时藏起幽灵、留下墨迹。射门路线用球门中点的直线，方式留空。这一步就可以把“补全再落笔”演示出来。弧线控件和射门方式控件可以后做，默认传球先落 `ground` / `straight`。

第三步做手绘和阵型。加上射线：传球两点、带球方向、射门方向和角度、方式与弧线。阵型可拖，并且只在这时打开环绕。载入另一条 jsonl 就能播生成器事后写出的演练。浏览器里不调用生成器。

## 7. 非目标

- 不删除、不替换联赛首页和 `touchline/scene`。
- 不设计联赛首页、阵容页、赛后文字报告。
- 不占用 5173，也不改 5174。
- 不加载左上角原点的 5 Hz 联赛追踪。
- v1 不接 Azure，不要求为了幽灵单独起服务。
- 幽灵不包含弧线、传球方式、射门方式，也不画 `secondary_pass`。
- 页面不生成演练片段，播放时不控制球员。
- 胶囊上不印俱乐部名或球员名。样本页现在也不印。
