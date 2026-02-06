/**
 * Envoy Orbital Logo Component
 * Three orbiting rings representing the three products in the suite
 */

interface OrbitalLogoProps {
  size?: number;
  showText?: boolean;
  className?: string;
}

export function OrbitalLogo({
  size = 40,
  showText = false,
  className = "",
}: OrbitalLogoProps) {
  return (
    <div className={`flex items-center gap-3 ${className}`}>
      <svg
        width={size}
        height={size}
        viewBox="0 0 120 120"
        className="orbital-logo"
      >
        <defs>
          <linearGradient id="orbitGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#191970" />
            <stop offset="100%" stopColor="#28a745" />
          </linearGradient>
        </defs>

        {/* Three orbiting rings representing the three products */}
        <ellipse
          cx="60"
          cy="60"
          rx="45"
          ry="20"
          fill="none"
          stroke="#191970"
          strokeWidth="1.5"
          opacity="0.3"
          style={{
            transformOrigin: "60px 60px",
            animation: "orbit-1 12s linear infinite",
          }}
        />

        <ellipse
          cx="60"
          cy="60"
          rx="45"
          ry="20"
          fill="none"
          stroke="#28a745"
          strokeWidth="1.5"
          opacity="0.4"
          style={{
            transformOrigin: "60px 60px",
            transform: "rotate(60deg)",
            animation: "orbit-2 12s linear infinite",
          }}
        />

        <ellipse
          cx="60"
          cy="60"
          rx="45"
          ry="20"
          fill="none"
          stroke="#764ba2"
          strokeWidth="1.5"
          opacity="0.4"
          style={{
            transformOrigin: "60px 60px",
            transform: "rotate(120deg)",
            animation: "orbit-3 12s linear infinite",
          }}
        />

        {/* Central core */}
        <circle
          cx="60"
          cy="60"
          r="8"
          fill="url(#orbitGrad)"
          style={{ animation: "pulse-core 3s ease-in-out infinite" }}
        />
        <circle cx="60" cy="60" r="4" fill="#28a745" opacity="0.8" />
      </svg>

      {showText && (
        <div className="flex flex-col">
          <div className="font-semibold text-2xl tracking-tight text-primary">
            Envoy
          </div>
          <div className="text-[10px] font-medium tracking-widest text-purple-600 uppercase">
            Financial Intelligence
          </div>
        </div>
      )}
    </div>
  );
}
