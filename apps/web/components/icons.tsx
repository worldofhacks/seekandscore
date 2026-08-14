import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

function IconFrame({ children, ...props }: IconProps) {
  return (
    <svg
      aria-hidden="true"
      fill="none"
      height="18"
      viewBox="0 0 24 24"
      width="18"
      {...props}
    >
      {children}
    </svg>
  );
}

const stroke = {
  stroke: "currentColor",
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  strokeWidth: 1.7,
};

export function GridIcon(props: IconProps) {
  return (
    <IconFrame {...props}>
      <rect height="7" rx="1" width="7" x="3" y="3" {...stroke} />
      <rect height="7" rx="1" width="7" x="14" y="3" {...stroke} />
      <rect height="7" rx="1" width="7" x="3" y="14" {...stroke} />
      <rect height="7" rx="1" width="7" x="14" y="14" {...stroke} />
    </IconFrame>
  );
}

export function QueueIcon(props: IconProps) {
  return (
    <IconFrame {...props}>
      <path d="M9 6h12M9 12h12M9 18h12" {...stroke} />
      <path d="M3.5 6h.01M3.5 12h.01M3.5 18h.01" stroke="currentColor" strokeLinecap="round" strokeWidth="3" />
    </IconFrame>
  );
}

export function MapIcon(props: IconProps) {
  return (
    <IconFrame {...props}>
      <path d="m3 5 6-2 6 2 6-2v16l-6 2-6-2-6 2V5Z" {...stroke} />
      <path d="M9 3v16M15 5v16" {...stroke} />
    </IconFrame>
  );
}

export function DealIcon(props: IconProps) {
  return (
    <IconFrame {...props}>
      <path d="M4 7h16v13H4zM8 7V4h8v3" {...stroke} />
      <path d="M4 12h16M10 12v2h4v-2" {...stroke} />
    </IconFrame>
  );
}

export function LockIcon(props: IconProps) {
  return (
    <IconFrame {...props}>
      <rect height="11" rx="2" width="16" x="4" y="10" {...stroke} />
      <path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3" {...stroke} />
    </IconFrame>
  );
}

export function PulseIcon(props: IconProps) {
  return (
    <IconFrame {...props}>
      <path d="M3 12h4l2.2-5 4.2 10 2.2-5H21" {...stroke} />
    </IconFrame>
  );
}

export function SearchIcon(props: IconProps) {
  return (
    <IconFrame {...props}>
      <circle cx="11" cy="11" r="6" {...stroke} />
      <path d="m16 16 4 4" {...stroke} />
    </IconFrame>
  );
}

export function ArrowUpIcon(props: IconProps) {
  return (
    <IconFrame {...props}>
      <path d="m6 14 6-6 6 6M12 8v11" {...stroke} />
    </IconFrame>
  );
}

export function ArrowDownIcon(props: IconProps) {
  return (
    <IconFrame {...props}>
      <path d="m6 10 6 6 6-6M12 5v11" {...stroke} />
    </IconFrame>
  );
}

export function ChevronRightIcon(props: IconProps) {
  return (
    <IconFrame {...props}>
      <path d="m9 5 7 7-7 7" {...stroke} />
    </IconFrame>
  );
}

export function CheckIcon(props: IconProps) {
  return (
    <IconFrame {...props}>
      <path d="m5 12 4 4L19 6" {...stroke} />
    </IconFrame>
  );
}

export function AlertIcon(props: IconProps) {
  return (
    <IconFrame {...props}>
      <path d="M12 3 2.8 20h18.4L12 3Z" {...stroke} />
      <path d="M12 9v5M12 17.5h.01" stroke="currentColor" strokeLinecap="round" strokeWidth="2" />
    </IconFrame>
  );
}

export function ClockIcon(props: IconProps) {
  return (
    <IconFrame {...props}>
      <circle cx="12" cy="12" r="9" {...stroke} />
      <path d="M12 7v5l3 2" {...stroke} />
    </IconFrame>
  );
}

export function ExternalIcon(props: IconProps) {
  return (
    <IconFrame {...props}>
      <path d="M14 4h6v6M20 4l-9 9" {...stroke} />
      <path d="M18 13v6H5V6h6" {...stroke} />
    </IconFrame>
  );
}

export function MoreIcon(props: IconProps) {
  return (
    <IconFrame {...props}>
      <circle cx="5" cy="12" fill="currentColor" r="1.3" />
      <circle cx="12" cy="12" fill="currentColor" r="1.3" />
      <circle cx="19" cy="12" fill="currentColor" r="1.3" />
    </IconFrame>
  );
}
