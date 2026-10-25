# 当前生成器上的决策分析集成

## 版本与变更边界

- 项目／数据基线：`96d13a377e98602c9998e3ebb82186843762febf`。
- 决策模块来源：Hackthon `84251bbdf1a8102ab4d6113c80da986adb38a461`。
- 目标是当前 NextPlay-AI 仓库；没有向 Hackthon 或远端推送更改。
- 保留当前 A 的生成器、比赛、赛程、统计、积分榜、报告和已有 API，不重新模拟比赛。
- 不接入 B 的旧 league 或 enriched-v1。新分析侧车全部关联当前 `data/league`。

本次核对 330 个来源文件哈希，与 B 新数据模块当时使用的 A 源完全一致；因此移植已经针对该源拟合的四折 xT、温度和 B0/B1 传球基线，并执行新版本全量评分、选择与绑定。没有把旧模型冒充新源重新训练结果，也没有声称主概率公式是新训练的神经网络。

## 模型

主模型仍为 B 的两步 Q2：候选 → 当前几何 → 战术结果概率 → 一步预测后继 → 再比较一次动作 → 12×8 xT 尾值。当前进球即时奖励为 1；本队延续加分，对手延续扣分；时间折扣为 exp(−动作秒数/120)。

Q = immediate + continuation − risk。分支概率是规则假设；xT 是当前合成源事件的空间尾值。B0/B1 树只蒸馏源传球规则作对照，不替换主概率。没有训练 FQI 或完整自主踢球策略。

兼容层读取明确攻向、分节终点、有效名单和实际门将角色。标准传球用球起点、接收者 0.25 秒速度前置和 14 m/s 地面球，与推演模板一致；越位、高球和场地支持掩码在两步均生效。高球和 hold 仍不排名、不假造零价值。

内部 Softmax 分数总和 100，最高项不强制 100；不是成功率或球员能力。新主表按用户要求用原因、风险替换净收益数字。完整数值仍在明确的诊断扩展 JSON 中。

来源 Sofascore 仅做来源画像和质量提示；惯用脚/弱脚保持中性。运动方向与身体朝向不同，未恢复视线、疲劳或个人技术质量。

## 页面整合

原 Analysis 内增加 Match report / Decision analysis 子页；原球员赛后报告、热力图和模型总结保留在 Match report 中。

Decision analysis 使用 B 原研究页的布局：球队／球员／动作／范围筛选，概要，决策时间线，快照，Player action conditions，候选排名／原因／风险，来源与证据详情。

- 默认最多 20 个代表节点：每球员≤2、每队≤10、同球权回合≤1、同球员相隔≥30 秒；按场区和球队轮换，不配平推荐动作比例。
- All decisions 查看全部快照，Largest value losses 单独用于失误复盘，Unavailable / coverage 展示不能分析的状态。
- 机会损失用实际类型／接收者匹配，不使用最终是否进球挑关键点。没有事前带球方向时不强制映射向前。
- 没有完整动画的位置仍可看精确快照。Open in replay 只在同一当前比赛的完整轨迹或预览覆盖下启用。
- 不再另开一个与主页面风格不同的决策首页。

`pitch-renderer.js` 从当前 Replay 提取，Replay、Decision analysis、Counterfactual lab 共同使用。草地条纹、白线、主橙／客蓝、号码、球和选中圈相同；候选线路只是额外覆盖，不替换球队配色。

主页面保留简洁，推演进入 `decision-counterfactual.html?match=...&decision=...&action=...`。返回链接恢复同一比赛、决策和本地筛选。更新主资源 URL，避免旧模块缓存；修复主页面初始化吞掉比赛深链接的问题。

## 反事实能力与限制

所有可分析节点的受支持 pass/carry/shot 均可进入详情并推演，不再只做少数固定案例。

传球复用 A 原物理循环，注入 B 排名的精确目标。带球和射门新增有明确边界的简化播放：速度上限 7.2 m/s、加速度 3.5 m/s²、50 ms 步长、最长 4 秒，当前分节边界截断。带球追目标并用近身接触近似丢球；射门为 24 m/s 直线地面球，近身封堵／门将接触判定，无反弹或个人能力。

四种反应／误差假设不是概率样本；3/4 或 4/4 成功不等于真实成功率。Q2 与播放使用不同后继近似；播放不反向改变 Q、排名或真实比赛。高球、hold、越位、不能分析的节点明确降级。

## 接口与后续 Agent

完整专用契约：`contracts/decision-analysis/README.md`。

- 原公共契约不改，新增 `/api/decision-analysis/compare` 输出原 rank/text-only。
- `/analyze` 返回 `decision-analysis-1`：完整 canonical request/snapshot、原 public 对象、球员条件、来源画像、30 个特征及单位、分支概率、Q1/Q2、Softmax、风险分解、判断、证据和版本。
- `/counterfactual` 是扩展的传／带／射接口；原 rollout 支持字段和 `/api/rollout` 仍为传球语义。
- `/context` 只返回登记的当前状态；客户端不能传任意未来帧。
- `/actual` 在计算后独立揭示历史类型／接收者，不输入主比较。
- Agent 可以读取指标并引用 evidence_ids；不能改排名或把假设写成观察。当前没有真实 Agent 调用，不伪造 trace。

Schema、工具目录和真实示例都位于 `contracts/decision-analysis/`。源文件更改、模型错配、过期候选集和非同源请求会拒绝。服务器运行期间也检查源文件签名，变化时重新核对哈希，而不是继续服务缓存的旧 metadata。

## 运行

原入口不变：`python3 server.py`，打开 `/`，选比赛 → Analysis → Decision analysis。

可深链接：`/?match=PL26-W01-MCI-CHE&view=stats&analysis=decisions`。

本地仓库只有一套当前比赛数据，不新增 Original/Enriched 切换。先前桌面 `启动NextPlay-AI.command` 已打开完整首页；新代码应启动新的服务进程，旧 Python 进程不会自动重新导入代码。启动器自动选择空闲端口，以终端实际打印地址为准。

## 复现与资源

`decision_analysis.pipeline` 保留 audit/train/score/validate，但输入为当前生成器 decision 快照，没有旧事件链推断兜底。默认 score 仅抽样，`score --all-decisions` 才全量；本次交付为全量。

源锁见 `docs/decision-source-lock.json`；metadata、事件、轨迹、球员数据和生成器等均有保护。模型、快照和结果放在 `data/decision-analysis`，不覆盖源。开发依赖可按 requirements-decision-analysis.txt 安装；网页运行只需 Python 标准库。

有关实测数量、耗时、原测试兼容和限制，见 `decision-analysis-validation.md`。源仓库跟踪的 node_modules 缺少 AJV dist，开发测试在临时副本使用独立已安装的 AJV 8.17.1/ajv-formats 3.0.1，未修改目标 node_modules；运行 Demo 本身无需这些依赖。
