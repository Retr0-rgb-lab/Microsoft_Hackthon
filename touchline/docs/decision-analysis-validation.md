# 决策分析移植验收记录

## 基线与来源

目标项目起点：`96d13a377e98602c9998e3ebb82186843762febf`。模块来源：Hackthon `84251bbdf1a8102ab4d6113c80da986adb38a461`。只将实现与同源分析侧车提交到桌面 NextPlay-AI，不修改 Hackthon 或推送远端。

移植前逐项校验 330 个 A 源文件，均与 B 新数据模型的 manifest 相同。移植同源拟合的四折 xT、温度和 B0/B1 基线；用新 `outcome-3.0` 比较器重新运行全量评分及代表性选择。没有运行比赛引擎，没有带入 B 的旧 league/enriched-v1。当前生成器、data/league、league-validated、原报告与回放未改。

## 实际数据

| 项目 | 结果 |
|---|---:|
| 比赛 | 40 |
| 规范精确快照 | 91,031 |
| 全量公开响应 | 91,031 |
| 有排名 / unknown | 91,029 / 2 |
| 全量推荐 pass / carry / shot | 62,004 / 24,512 / 4,513 |
| 代表性节点 | 800，40 场各 20 |
| 每场代表球员 | 19–20 名 |
| 代表节点推荐 pass / carry / shot | 652 / 76 / 72 |
| 新侧车发布大小 | 97,293,829 bytes，约 97.29 MB / 92.79 MiB |
| 全量评分耗时 | 本机 372.64 秒 |
| 在线／预计算比对 | 40 场首尾共 80 个节点，逐项相同；桌面目标副本另行复核通过 |

两个 unknown 是未满足正常比赛持球条件的最终节点，不提供虚假排名或推演。历史带球没有事前方向时保持匹配未知。源中只有四场完整 tracking，其余逐决策快照可用；回放跳转必须受实际轨迹覆盖约束。

这些比例是描述性统计，不是精度分数；没有硬性压低射门推荐占比。代表性约束为每人≤2、每队≤10、每球权回合≤1、同球员间隔≥30 秒。场区与球队轮换，不伪造缺失球员。

## 自动验证

| 检查 | 结果 |
|---|---|
| 原有及新增 Python 全集 | 107 项通过；最终新增集成测试 8 项再次通过 |
| JavaScript 全集 | 24 项通过 |
| 原 canonical 契约回归 | 包含原测试与移植的 14 项专门回归，通过 |
| 源数据原 Schema | root data 与 league 全部核心记录通过；league：40 metadata、40 previews、150,466 events、240,040 states、211,035 tracking（含 91,031 决策帧） |
| 新侧车语义验证 | 40 场、91,031 snapshots、91,031 public responses；原件保护、哈希、引用和留出折隔离通过 |
| 新扩展 Schema | 编译及实际 context/analyze/counterfactual 示例通过；catalog/index 在 HTTP 测试通过 |
| 全量侧车 Schema | metadata、index、snapshot、public response 全量通过，具体数量见运行记录 |
| 传球／带球／射门推演 | 相同状态／动作／版本可重复；帧零保持观测，后续速度≤7.2 m/s，位置有限，四情景≤4 秒，半场终点截断 |
| 过期／错误请求 | 错候选 ID、未知路径、越权源、未来结果输入、不支持动作被拒绝 |
| 源更新防串数据 | 启动哈希与运行期文件签名／变化后哈希检查；不因内存 metadata 缓存忽略重新生成的源 |
| 原 API 回归 | 旧 decision/rollout、模型设置、赛后总结、Agent API 保持独立；不修改 canonical Schema |

Schema 校验与数值回归不证明真实足球反事实准确。Q2 的战术分支仍是规则假设，传球树仍只是源机制蒸馏基线。

## 页面联调

- 原首页、Analysis/Match report、Decision analysis、同一比赛 Replay 入口正常。
- 新页面使用原研究页的时间线／筛选布局，Player action conditions 保留，主表显示原因与风险。
- 同一 `pitch-renderer.js` 供 Replay、决策和推演使用：原草地条纹、线条、主橙客蓝、球员号码和球保留。
- 40 场索引完整；快速选择取消／丢弃旧状态，版本绑定检查仍在。
- 反事实二级页：传、带、射均完成计算／播放／重置；返回同比赛与同决策。
- 1280 桌面和 390 手机检查；两种新页面手机整页宽度为 390，无整页横向溢出，候选表在自身容器内滚动。
- 新资源版本参数已升级，避免与旧项目脚本混用；重启 Python 后使用新进程端口。

## 测试环境和诚实边界

Python 完整测试使用独立 Python 3.12 环境；网页预览和新专门回归也在系统 Python 3.9 运行。运行 Demo 不需 scikit-learn、Node 或 API Key；离线重新拟合才需训练依赖。

A 仓库跟踪的 node_modules 缺 AJV dist。临时开发副本的 offline 安装尝试未取得所需缓存后，改用隔离的已安装 AJV 8.17.1 / ajv-formats 3.0.1 依赖完成开发测试，没有把 node_modules 修改复制回目标仓库。Node 加入 PATH 后运行 Schema 子进程；没有伪称未经依赖准备的原环境就能通过。

没有配置或调用真实解释 Agent；返回 model_unavailable、null explanation、空 trace，但数值及原因风险仍可用。新增数值是明确的 research extension，原公共对象依旧无 Q/Softmax。hold、高球、空中对抗、个人技能、真实身体姿态和长程完整策略未实现。

带球／射门反事实是本次新增的有界简化播放，不是完整物理比赛引擎。与 Q2 的后继近似不完全一致，不能用四个动画情景反向认证主模型。后续接 Agent 应按专用契约引用字段、声明假设、拒绝过期候选，不篡改排名。

## 主要命令

```sh
node --test tests/*.test.js
python3 -m unittest discover -s tests -p 'test_*.py'
node scripts/validate_contracts.mjs --dataset data data/league
node scripts/validate_decision_analysis.mjs
node scripts/validate_decision_dataset.mjs
python3 -m decision_analysis.pipeline validate
```

统计机器可读副本：`decision-analysis-metrics.json`。所有源码／源数据改动检查均在最终提交前核对。

桌面目标副本复核：系统 Python 3.9.6 可加载完整指标并计算三类推演；24 项 JavaScript 测试通过；目标位置 80 个在线／预计算边界响应一致，原源文件哈希未变。最终预览从目标仓库的新进程提供，不复用旧进程。
