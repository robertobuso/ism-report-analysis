/**
 * Envoy Signal Logo - Static (matches Flask navbar)
 * Signal waves representing financial intelligence
 */

interface EnvoyLogoProps {
  size?: number;
  className?: string;
}

export function EnvoyLogo({ size = 40, className = "" }: EnvoyLogoProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 120 120"
      className={`inline-block ${className}`}
      style={{ verticalAlign: "middle" }}
    >
      <defs>
        <linearGradient
          id="signalGradStatic"
          x1="0%"
          y1="100%"
          x2="0%"
          y2="0%"
        >
          <stop offset="0%" stopColor="#191970" stopOpacity="0.3" />
          <stop offset="50%" stopColor="#764ba2" stopOpacity="0.7" />
          <stop offset="100%" stopColor="#28a745" />
        </linearGradient>
        <linearGradient id="coreGradStatic" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#28a745" />
          <stop offset="100%" stopColor="#3b82f6" />
        </linearGradient>
      </defs>

      {/* Static signal waves */}
      <path
        d="M 30 60 Q 60 36, 90 60"
        fill="none"
        stroke="url(#signalGradStatic)"
        strokeWidth="2"
        opacity="0.8"
      />

      <path
        d="M 36 60 Q 60 40, 84 60"
        fill="none"
        stroke="url(#signalGradStatic)"
        strokeWidth="2"
        opacity="0.65"
      />

      <path
        d="M 42 60 Q 60 44, 78 60"
        fill="none"
        stroke="url(#signalGradStatic)"
        strokeWidth="2"
        opacity="0.5"
      />

      <path
        d="M 48 60 Q 60 48, 72 60"
        fill="none"
        stroke="url(#signalGradStatic)"
        strokeWidth="2"
        opacity="0.35"
      />

      <path
        d="M 54 60 Q 60 52, 66 60"
        fill="none"
        stroke="url(#signalGradStatic)"
        strokeWidth="2"
        opacity="0.2"
      />

      {/* Static source point */}
      <circle cx="60" cy="60" r="5" fill="url(#coreGradStatic)" />
      <circle cx="60" cy="60" r="3" fill="#3b82f6" />
    </svg>
  );
}
