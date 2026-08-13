import type {
  ButtonHTMLAttributes,
  HTMLAttributes,
  PropsWithChildren,
  ReactNode,
} from "react";

type ButtonVariant = "primary" | "secondary" | "quiet" | "danger";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: "small" | "medium";
}

export function Button({
  className = "",
  variant = "secondary",
  size = "medium",
  type = "button",
  ...props
}: ButtonProps) {
  return (
    <button
      className={`ui-button ui-button--${variant} ui-button--${size} ${className}`.trim()}
      type={type}
      {...props}
    />
  );
}

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  label: string;
  children: ReactNode;
}

export function IconButton({ label, className = "", children, type = "button", ...props }: IconButtonProps) {
  return (
    <button
      aria-label={label}
      className={`ui-icon-button ${className}`.trim()}
      title={label}
      type={type}
      {...props}
    >
      {children}
    </button>
  );
}

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: "neutral" | "accent" | "outline" | "blocked";
}

export function Badge({ tone = "neutral", className = "", ...props }: BadgeProps) {
  return <span className={`ui-badge ui-badge--${tone} ${className}`.trim()} {...props} />;
}

export interface PanelProps extends PropsWithChildren<HTMLAttributes<HTMLElement>> {
  as?: "section" | "article" | "aside" | "div";
}

export function Panel({ as: Component = "section", className = "", ...props }: PanelProps) {
  return <Component className={`ui-panel ${className}`.trim()} {...props} />;
}

export function VisuallyHidden({ children }: PropsWithChildren) {
  return <span className="ui-visually-hidden">{children}</span>;
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <span className="ui-spinner" role="status">
      <span aria-hidden="true" className="ui-spinner__mark" />
      <VisuallyHidden>{label}</VisuallyHidden>
    </span>
  );
}
