import type { ActionClass, AgentRole, Language } from "./types";
import type { Phase } from "./machine";

const en = {
  product: "Inside the Game",
  flow: "Decision flow",
  sub: "Synthetic clip · four-class decision",
  fictional: "Fictional squads only",
  language: "Language",
  mode: "Mode",
  fan: "Fan",
  coach: "Coach",
  playback: "Playback",
  play: "Play",
  pause: "Pause",
  moments: "Moments",
  questions: "Questions",
  analyze: "Compare actions",
  loading: "Reading the frame…",
  distribution: "Model distribution",
  distributionNote: "Shares across pass, shoot, dribble, and hold. Not a completion percentage.",
  primary: "Primary",
  secondary: "Secondary",
  recorded: "Recorded",
  other: "Other class",
  preview: "Play hypothetical",
  reset: "Reset snapshot",
  explain: "Explanation",
  backDist: "Back to distribution",
  pickPrompt: "Pick a class first. The distribution stays hidden until you reveal it.",
  reveal: "Reveal analysis",
  traceSummary: "Agent process",
  limitations: "Limitations",
  retry: "Retry agent text",
  dropped: "Agent text was dropped because the candidate set did not match. The distribution is still shown.",
  notCarrier: "That player does not have the ball at this decision.",
  wait: "Let the clip reach a decision, or pick a moment.",
  playingHint: "Playing the synthetic clip. It pauses at the next on-ball decision.",
  pausedHint: "Paused before the carrier commits. Ask a question, then compare.",
  selectingHint: "Question ready. Compare when you want the distribution.",
  enterTitle: "Pause before the choice",
  enterBody: "A fictional match runs until the carrier is about to act. Then compare pass, shoot, dribble, and hold.",
  enterAction: "Play synthetic match",
  broadcast: "Broadcast",
  topdown: "Top-down",
  legendRecorded: "Solid · what happened",
  legendOther: "Dashed · other class",
  hypo: "Hypothetical / 假设推演",
  diagram: "Top-down paths",
  speed: "Speed",
  spaceHint: "Space pauses. 1 broadcast, 2 top-down.",
  sampleLink: "Pitch sample",
  aid: "Decision aid. Not a grade on the player.",
  yourPick: "Your pick",
  emptyAsk: "Pick a moment or keep playing to the next decision.",
  previewHint: "Hypothetical path on the frozen snapshot. Reset returns to the same frame.",
  explainHint: "Fan and coach read the same distribution at different depth.",
  passPath: "Pass",
  dribblePath: "Dribble",
  shotSeg: "Shot",
  holdRing: "Hold",
  role_coordinator: "Coordinator",
  role_attack: "Attack",
  role_defense: "Defense",
  role_review: "Review",
  phase_enter: "Ready",
  phase_playing: "Playing",
  phase_paused: "Paused",
  phase_selecting: "Question",
  phase_loading: "Loading",
  phase_deciding: "Distribution",
  phase_preview: "Hypothetical",
  phase_explaining: "Explanation",
  action_pass: "Pass",
  action_shoot: "Shoot",
  action_dribble: "Dribble",
  action_hold: "Hold",
};

const zh: typeof en = {
  product: "Inside the Game",
  flow: "决策流程",
  sub: "合成片段 · 四类动作",
  fictional: "仅虚构球队",
  language: "语言",
  mode: "模式",
  fan: "球迷",
  coach: "训练复盘",
  playback: "回放",
  play: "播放",
  pause: "暂停",
  moments: "时刻",
  questions: "问题",
  analyze: "比较动作",
  loading: "正在读取这一帧…",
  distribution: "模型分布",
  distributionNote: "传球、射门、带球、等待的份额。不是完成百分比。",
  primary: "主推荐",
  secondary: "次选",
  recorded: "实际发生",
  other: "其他类别",
  preview: "播放假设",
  reset: "回到快照",
  explain: "解释",
  backDist: "返回分布",
  pickPrompt: "先自己选一个类别。揭示之前不显示分布。",
  reveal: "揭示分析",
  traceSummary: "Agent 过程",
  limitations: "限制",
  retry: "重试 Agent 文本",
  dropped: "候选集不一致，已丢弃 Agent 文本。分布仍然显示。",
  notCarrier: "这个决策时刻，球不在这名球员脚下。",
  wait: "请等到决策点，或从时刻列表进入。",
  playingHint: "正在播放合成比赛，下一处持球决策会自动暂停。",
  pausedHint: "已停在球员做决定之前。先提问，再比较。",
  selectingHint: "问题已选好。需要分布时再比较。",
  enterTitle: "在出脚之前暂停",
  enterBody: "虚构比赛会播到持球人即将做决定。然后比较传球、射门、带球和等待。",
  enterAction: "播放合成比赛",
  broadcast: "转播",
  topdown: "俯视",
  legendRecorded: "实线 · 实际发生",
  legendOther: "虚线 · 其他类别",
  hypo: "Hypothetical / 假设推演",
  diagram: "俯视路径",
  speed: "速度",
  spaceHint: "空格暂停。1 转播，2 俯视。",
  sampleLink: "球场示例",
  aid: "决策辅助。不是对球员的评分。",
  yourPick: "你的选择",
  emptyAsk: "选一个时刻，或继续播放到下一处决策。",
  previewHint: "在冻结的快照上播放假设路径。重置会回到同一帧。",
  explainHint: "球迷和训练复盘读的是同一分布，深度不同。",
  passPath: "传球",
  dribblePath: "带球",
  shotSeg: "射门",
  holdRing: "等待",
  role_coordinator: "协调",
  role_attack: "进攻",
  role_defense: "防守",
  role_review: "审查",
  phase_enter: "准备",
  phase_playing: "播放",
  phase_paused: "暂停",
  phase_selecting: "提问",
  phase_loading: "读取",
  phase_deciding: "分布",
  phase_preview: "假设",
  phase_explaining: "解释",
  action_pass: "传球",
  action_shoot: "射门",
  action_dribble: "带球",
  action_hold: "等待",
};

export const copy = { en, zh };

export type CopyKey = keyof typeof en;

export function text(language: Language, key: CopyKey): string {
  return copy[language][key];
}

export function applyI18n(root: ParentNode, language: Language): void {
  root.querySelectorAll<HTMLElement>("[data-i18n]").forEach((el) => {
    const key = el.dataset.i18n as CopyKey | undefined;
    if (!key || !(key in copy.en)) return;
    el.textContent = copy[language][key];
  });
}

export function actionName(action: ActionClass, language: Language): string {
  return text(language, `action_${action}`);
}

export function phaseName(phase: Phase, language: Language): string {
  return text(language, `phase_${phase}`);
}

export function roleName(role: AgentRole, language: Language): string {
  return text(language, `role_${role}`);
}
