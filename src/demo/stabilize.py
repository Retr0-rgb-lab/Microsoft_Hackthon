"""Temporal hold for the recommendation and the arrows drawn around it.

The softmax argmax and the top pass can swap on adjacent frames when feet
jitter by a metre. Displayed probabilities are an exponential average. The
highlighted action changes only after the new leader has stayed ahead, and a
pass arrow stays on the same teammate until they are no longer a legal
receiver.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from demo.options import (
    PRIMARY_ALPHA,
    SECONDARY_ALPHA,
    OptionPlayer,
    TacticalOption,
    is_opponent_goalkeeper,
    opponent_goal,
    pass_window,
)
from inside_the_game.labels import ACTION_LABELS


@dataclass
class OverlayMemory:
    """Stateful smoother. Reset on a scene cut or a new possessor."""

    switch_frames: int = 6
    enter_frames: int = 4
    grace_frames: int = 8
    lead_margin: float = 0.08
    force_margin: float = 0.20
    ema: float = 0.30
    possessor_id: int | None = None
    shown: dict[str, float] | None = None
    label: str | None = None
    pending: str | None = None
    pending_count: int = 0
    shown_passes: list[int] = field(default_factory=list)
    pass_pending: dict[int, int] = field(default_factory=dict)
    pass_absent: dict[int, int] = field(default_factory=dict)
    primary_slot: str | None = None
    primary_pending: str | None = None
    primary_count: int = 0
    shot_absent: int = 0
    shot_seen: bool = False

    def reset(self) -> None:
        self.possessor_id = None
        self.shown = None
        self.label = None
        self.pending = None
        self.pending_count = 0
        self.shown_passes = []
        self.pass_pending = {}
        self.pass_absent = {}
        self.primary_slot = None
        self.primary_pending = None
        self.primary_count = 0
        self.shot_absent = 0
        self.shot_seen = False

    def apply(
        self,
        possessor_id: int,
        probabilities: dict[str, float],
        options: list[TacticalOption],
        players: list[OptionPlayer],
        origin: tuple[float, float],
        possessor_team: str,
        bounds: tuple[float, float],
        attacking_positive: bool,
        space: str,
    ) -> tuple[str, dict[str, float], list[TacticalOption]]:
        if possessor_id != self.possessor_id:
            self.reset()
            self.possessor_id = possessor_id
        recommended = self._hold_label(probabilities)
        assert self.shown is not None
        chosen = self._hold_options(
            options,
            players,
            origin,
            possessor_team,
            bounds,
            attacking_positive,
            space,
            recommended,
        )
        return recommended, dict(self.shown), chosen

    def _hold_label(self, probabilities: dict[str, float]) -> str:
        fresh = {label: float(probabilities[label]) for label in ACTION_LABELS}
        if self.shown is None or self.label is None:
            self.shown = fresh
            self.label = max(fresh, key=fresh.get)
            self.pending = None
            self.pending_count = 0
            return self.label
        blended = {
            label: (1.0 - self.ema) * self.shown[label] + self.ema * fresh[label]
            for label in ACTION_LABELS
        }
        total = sum(blended.values()) or 1.0
        self.shown = {label: value / total for label, value in blended.items()}
        leader = max(self.shown, key=self.shown.get)
        if leader == self.label:
            self.pending = None
            self.pending_count = 0
            return self.label
        lead = self.shown[leader] - self.shown[self.label]
        if lead < self.lead_margin:
            self.pending = None
            self.pending_count = 0
            return self.label
        if self.pending != leader:
            self.pending = leader
            self.pending_count = 1
        else:
            self.pending_count += 1
        if self.pending_count >= self.switch_frames or lead >= self.force_margin:
            self.label = leader
            self.pending = None
            self.pending_count = 0
        return self.label

    def _hold_options(
        self,
        options: list[TacticalOption],
        players: list[OptionPlayer],
        origin: tuple[float, float],
        possessor_team: str,
        bounds: tuple[float, float],
        attacking_positive: bool,
        space: str,
        recommended: str,
    ) -> list[TacticalOption]:
        mates = {
            player.track_id: player
            for player in players
            if player.track_id != self.possessor_id
            and player.role != "referee"
            and player.team == possessor_team
            and possessor_team in ("home", "away")
            and not is_opponent_goalkeeper(player, attacking_positive, bounds)
        }
        by_id = {
            item.target_id: item
            for item in options
            if item.kind == "pass" and item.target_id in mates
        }
        for target_id in list(self.pass_pending):
            if target_id not in by_id:
                self.pass_pending[target_id] = 0
        for target_id in by_id:
            self.pass_pending[target_id] = self.pass_pending.get(target_id, 0) + 1

        low, high = pass_window(bounds, space)
        selected: list[int] = []
        for target_id in self.shown_passes:
            player = mates.get(target_id)
            if player is None:
                self.pass_absent.pop(target_id, None)
                continue
            distance = _dist(origin, player.xy)
            legal = target_id in by_id or low * 0.7 <= distance <= high * 1.2
            if not legal:
                missed = self.pass_absent.get(target_id, 0) + 1
                self.pass_absent[target_id] = missed
                if missed > self.grace_frames:
                    continue
            else:
                self.pass_absent[target_id] = 0
            selected.append(target_id)

        ranked = sorted(by_id, key=lambda target_id: by_id[target_id].score, reverse=True)
        if not self.shown_passes:
            for target_id in ranked:
                if target_id not in selected:
                    selected.append(target_id)
                if len(selected) >= 3:
                    break
        else:
            for target_id in ranked:
                if target_id in selected:
                    continue
                if self.pass_pending.get(target_id, 0) >= self.enter_frames:
                    selected.append(target_id)
                if len(selected) >= 3:
                    break
        selected = selected[:3]
        self.shown_passes = list(selected)

        built: list[TacticalOption] = []
        for target_id in selected:
            player = mates[target_id]
            score = by_id[target_id].score if target_id in by_id else 0.0
            built.append(
                TacticalOption(
                    kind="pass",
                    origin=origin,
                    target=player.xy,
                    score=score,
                    primary=False,
                    alpha=SECONDARY_ALPHA,
                    label="pass",
                    target_id=target_id,
                    slot=f"pass:{target_id}",
                )
            )

        carries = [item for item in options if item.kind == "dribble"]
        carries.sort(key=lambda item: item.slot)
        built.extend(carries)

        shot_now = next((item for item in options if item.kind == "shoot"), None)
        if shot_now is not None:
            self.shot_seen = True
            self.shot_absent = 0
        elif self.shot_seen:
            self.shot_absent += 1
        if shot_now is not None or (self.shot_seen and self.shot_absent <= self.grace_frames):
            score = shot_now.score if shot_now is not None else 0.01
            built.append(
                TacticalOption(
                    kind="shoot",
                    origin=origin,
                    target=opponent_goal(bounds, attacking_positive),
                    score=score,
                    primary=False,
                    alpha=SECONDARY_ALPHA,
                    label="shot",
                    slot="shoot:goal",
                )
            )

        hold = next((item for item in options if item.kind == "hold"), None)
        if hold is not None:
            built.append(
                TacticalOption(
                    kind="hold",
                    origin=origin,
                    target=origin,
                    score=hold.score,
                    primary=False,
                    alpha=SECONDARY_ALPHA,
                    label="hold",
                    slot="hold",
                )
            )
        return _mark_slot(built, self._primary_slot(built, recommended))

    def _primary_slot(self, options: list[TacticalOption], recommended: str) -> str | None:
        candidates = [item for item in options if item.kind == recommended and item.slot]
        if not candidates:
            self.primary_slot = None
            self.primary_pending = None
            self.primary_count = 0
            return None
        best = max(candidates, key=lambda item: item.score)
        slots = {item.slot for item in candidates}
        if self.primary_slot not in slots:
            self.primary_slot = best.slot
            self.primary_pending = None
            self.primary_count = 0
            return self.primary_slot
        if best.slot == self.primary_slot:
            self.primary_pending = None
            self.primary_count = 0
            return self.primary_slot
        current = next(item for item in candidates if item.slot == self.primary_slot)
        if best.score <= current.score + 0.04:
            self.primary_pending = None
            self.primary_count = 0
            return self.primary_slot
        if self.primary_pending != best.slot:
            self.primary_pending = best.slot
            self.primary_count = 1
        else:
            self.primary_count += 1
        if self.primary_count >= self.switch_frames:
            self.primary_slot = best.slot
            self.primary_pending = None
            self.primary_count = 0
        return self.primary_slot


def _mark_slot(options: list[TacticalOption], slot: str | None) -> list[TacticalOption]:
    if slot is None:
        return options
    marked: list[TacticalOption] = []
    for item in options:
        primary = item.slot == slot
        marked.append(
            TacticalOption(
                kind=item.kind,
                origin=item.origin,
                target=item.target,
                score=item.score,
                primary=primary,
                alpha=PRIMARY_ALPHA if primary else item.alpha,
                label=item.label,
                target_id=item.target_id,
                slot=item.slot,
            )
        )
    marked.sort(key=lambda item: (item.primary, item.slot))
    return marked


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
