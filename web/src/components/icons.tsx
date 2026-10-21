import type { ReactNode } from "react";

type IconProps = { className?: string };

function Svg({ className, children }: IconProps & { children: ReactNode }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      {children}
    </svg>
  );
}

export function IconFolder() {
  return (
    <Svg>
      <path d="M3.5 8.2V18a1.5 1.5 0 0 0 1.5 1.5h14A1.5 1.5 0 0 0 20.5 18V9.8a1.5 1.5 0 0 0-1.5-1.5h-7.2L9.6 6.2H5A1.5 1.5 0 0 0 3.5 7.7v.5Z" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
    </Svg>
  );
}

export function IconSave() {
  return (
    <Svg>
      <path d="M6 3.8h9.2L20 8.6V20a1.2 1.2 0 0 1-1.2 1.2H6A1.2 1.2 0 0 1 4.8 20V5A1.2 1.2 0 0 1 6 3.8Z" fill="none" stroke="currentColor" strokeWidth="1.6" />
      <path d="M8 3.8v5h7.2v-5" fill="none" stroke="currentColor" strokeWidth="1.6" />
      <path d="M8 14.2h8.2V21H8z" fill="currentColor" />
    </Svg>
  );
}

export function IconGear() {
  return (
    <Svg>
      <circle cx="12" cy="12" r="3" fill="none" stroke="currentColor" strokeWidth="1.6" />
      <path d="M12 3.4v2.2M12 18.4v2.2M3.4 12h2.2M18.4 12h2.2M5.8 5.8l1.6 1.6M16.6 16.6l1.6 1.6M18.2 5.8l-1.6 1.6M7.4 16.6l-1.6 1.6" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </Svg>
  );
}

export function IconPlay() {
  return (
    <Svg>
      <path d="M9 7.2v9.6l8-4.8-8-4.8Z" fill="currentColor" />
    </Svg>
  );
}

export function IconPause() {
  return (
    <Svg>
      <path d="M8 6.5h2.6v11H8zM13.4 6.5H16v11h-2.6z" fill="currentColor" />
    </Svg>
  );
}

export function IconFullscreen() {
  return (
    <Svg>
      <path d="M9 4.5H4.5V9M15 4.5h4.5V9M9 19.5H4.5V15M15 19.5h4.5V15" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </Svg>
  );
}

export function IconPass() {
  return (
    <Svg>
      <path d="M4 12h12.5M13 7.2 18.8 12 13 16.8" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}

export function IconShoot() {
  return (
    <Svg>
      <rect x="4" y="6" width="16" height="12" rx="1.6" fill="none" stroke="currentColor" strokeWidth="1.7" />
      <circle cx="12" cy="12" r="2.1" fill="currentColor" />
    </Svg>
  );
}

export function IconDribble() {
  return (
    <Svg>
      <circle cx="6" cy="16" r="1.7" fill="currentColor" />
      <circle cx="12" cy="11" r="1.7" fill="currentColor" />
      <circle cx="18" cy="6.5" r="1.7" fill="currentColor" />
    </Svg>
  );
}

export function IconHold() {
  return (
    <Svg>
      <circle cx="12" cy="12" r="7" fill="none" stroke="currentColor" strokeWidth="1.7" />
      <path d="M12 8.2V12l2.6 1.7" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </Svg>
  );
}
