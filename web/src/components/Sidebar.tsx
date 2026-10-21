import type { ComponentType } from "react";
import { ACTIONS } from "../types";
import type { Action, Moment } from "../types";
import { formatPercent, SIDEBAR_HIGHLIGHT } from "../display";
import { IconDribble, IconHold, IconPass, IconShoot } from "./icons";
import { MiniPitch } from "./MiniPitch";

const ICONS: Record<Action, ComponentType> = {
  pass: IconPass,
  shoot: IconShoot,
  dribble: IconDribble,
  hold: IconHold,
};

type SidebarProps = {
  moment: Moment;
  disclaimer: string;
};

export function Sidebar({ moment, disclaimer }: SidebarProps) {
  return (
    <aside className="sidebar" data-testid="sidebar" style={{ ["--softmax" as string]: SIDEBAR_HIGHLIGHT }}>
      <section>
        <h2>ON-BALL OPTIONS</h2>
        <div className="options" role="list">
          {ACTIONS.map((action) => {
            const probability = moment.distribution[action];
            const primary = action === moment.recommended;
            const Icon = ICONS[action];
            const percent = formatPercent(probability);
            return (
              <div
                key={action}
                className={primary ? "opt is-primary" : "opt"}
                role="listitem"
                data-testid={`bar-${action}`}
                aria-label={`${action} ${percent}`}
              >
                <Icon />
                <span className="opt-label">{action}</span>
                {primary ? (
                  <span />
                ) : (
                  <span className="meter" aria-hidden="true">
                    <span
                      className={action === "hold" ? "fill is-hold" : "fill"}
                      style={{ width: `${Math.max(0, Math.min(100, probability * 100))}%` }}
                    />
                  </span>
                )}
                <span className="percent" data-testid={`percent-${action}`}>
                  {percent}
                </span>
              </div>
            );
          })}
        </div>
      </section>
      <section>
        <h2>PRIMARY EXPLAIN</h2>
        <p data-testid="primary-explain">{moment.primary_explain}</p>
      </section>
      <section>
        <h2>SECONDARY EXPLAIN</h2>
        <p data-testid="secondary-explain">{moment.secondary_explain}</p>
      </section>
      <section>
        <h2>SYSTEM2 RATIONALE:</h2>
        <p data-testid="system2">{moment.system2_rationale}</p>
      </section>
      <section className="minimap-section">
        <h2>MINIMAP (PITCH)</h2>
        <div className="minimap-wrap">
          <MiniPitch moment={moment} />
        </div>
      </section>
      <section>
        <p className="disclaimer" data-testid="disclaimer">
          {disclaimer}
        </p>
      </section>
    </aside>
  );
}
