import markAnimated from "../assets/brand/mark-animated.svg";

type Props = {
  size?: number;
  label?: string;
  className?: string;
};

export function LoadingMark({ size = 72, label = "Loading…", className }: Props) {
  return (
    <div
      className={`loading-mark${className ? ` ${className}` : ""}`}
      role="status"
      aria-live="polite"
    >
      <img
        src={markAnimated}
        alt=""
        width={size}
        height={size}
        className="loading-mark-svg"
      />
      {label ? <span className="loading-mark-label">{label}</span> : null}
    </div>
  );
}
