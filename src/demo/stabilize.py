"""Temporal hold for the recommendation and the single arrow drawn for it.

The softmax argmax can swap on adjacent frames when feet jitter. Displayed
probabilities are an exponential average, and the highlighted class changes
only after the new leader has stayed ahead. A pass arrow stays on the same
visible teammate until a better receiver has earned the switch. Shoot and
hold are not drawn.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from demo.options import (
    PRIMARY_ALPHA,
    OptionPlayer,
    TacticalOption,
    build_options,
    eligible_receivers,
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
        """One primary arrow for the held class. Dim alternatives are added at draw time."""
        mates = eligible_receivers(
            players,
            -1 if self.possessor_id is None else self.possessor_id,
            possessor_team,
            attacking_positive,
            bounds,
        )
        if recommended == "pass":
            return self._one_pass(options, mates, players, origin, possessor_team, bounds, attacking_positive, space)
        if recommended == "dribble":
            self.shown_passes = []
            return self._one_dribble(
                options, players, origin, possessor_team, bounds, attacking_positive, space
            )
        self.shown_passes = []
        return []

    def _one_pass(
        self,
        options: list[TacticalOption],
        mates: dict[int, OptionPlayer],
        players: list[OptionPlayer],
        origin: tuple[float, float],
        possessor_team: str,
        bounds: tuple[float, float],
        attacking_positive: bool,
        space: str,
    ) -> list[TacticalOption]:
        low, high = pass_window(bounds, space)
        if not any(item.kind == "pass" for item in options) and self.possessor_id is not None:
            options = build_options(
                origin,
                players,
                self.possessor_id,
                possessor_team,
                "pass",
                bounds=bounds,
                attacking_positive=attacking_positive,
                space=space,
            )
            # The hold compares the locked receiver with the single best pass.
            # Extra dim passes must not change that decision.
            options = [item for item in options if item.primary] or options[:1]
        incoming = {
            item.target_id: item
            for item in options
            if item.kind == "pass" and item.target_id in mates
        }
        stored = self.shown_passes[0] if self.shown_passes else None
        if stored not in mates:
            stored = None
        else:
            distance = _dist(origin, mates[stored].xy)
            if not low * 0.75 <= distance <= high * 1.05:
                stored = None
        best = max(incoming.values(), key=lambda item: item.score) if incoming else None
        chosen = stored
        if chosen is None:
            self.pass_pending.clear()
            chosen = None if best is None else best.target_id
        elif best is not None and best.target_id != chosen:
            current_score = incoming[chosen].score if chosen in incoming else None
            better = current_score is None or best.score > current_score + 0.04
            if not better:
                self.pass_pending.clear()
            else:
                count = self.pass_pending.get(best.target_id, 0) + 1
                self.pass_pending = {best.target_id: count}
                if count >= self.enter_frames:
                    chosen = best.target_id
                    self.pass_pending.clear()
        else:
            self.pass_pending.clear()
        if chosen is None or chosen not in mates:
            self.shown_passes = []
            return []
        self.shown_passes = [chosen]
        player = mates[chosen]
        score = incoming[chosen].score if chosen in incoming else 0.0
        return [
            TacticalOption(
                kind="pass",
                origin=origin,
                target=player.xy,
                score=score,
                primary=True,
                alpha=PRIMARY_ALPHA,
                label="pass",
                target_id=chosen,
                slot=f"pass:{chosen}",
            )
        ]

    def _one_dribble(
        self,
        options: list[TacticalOption],
        players: list[OptionPlayer],
        origin: tuple[float, float],
        possessor_team: str,
        bounds: tuple[float, float],
        attacking_positive: bool,
        space: str,
    ) -> list[TacticalOption]:
        carries = [item for item in options if item.kind == "dribble"]
        if not carries and self.possessor_id is not None:
            carries = build_options(
                origin,
                players,
                self.possessor_id,
                possessor_team,
                "dribble",
                bounds=bounds,
                attacking_positive=attacking_positive,
                space=space,
            )
        carries = [item for item in carries if item.kind == "dribble"]
        if not carries:
            return []
        best = max(carries, key=lambda item: item.score)
        by_slot = {item.slot: item for item in carries}
        chosen = best
        if self.primary_slot in by_slot and self.primary_slot != best.slot:
            current = by_slot[self.primary_slot]
            if best.score <= current.score + 0.15:
                chosen = current
                self.primary_pending = None
                self.primary_count = 0
            else:
                if self.primary_pending != best.slot:
                    self.primary_pending = best.slot
                    self.primary_count = 1
                else:
                    self.primary_count += 1
                if self.primary_count < self.switch_frames:
                    chosen = current
                else:
                    self.primary_pending = None
                    self.primary_count = 0
        else:
            self.primary_pending = None
            self.primary_count = 0
        self.primary_slot = chosen.slot
        return [
            TacticalOption(
                kind="dribble",
                origin=chosen.origin,
                target=chosen.target,
                score=chosen.score,
                primary=True,
                alpha=PRIMARY_ALPHA,
                label="carry",
                target_id=None,
                slot=chosen.slot,
            )
        ]


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
