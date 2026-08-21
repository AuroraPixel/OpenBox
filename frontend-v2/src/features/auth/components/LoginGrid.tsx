import type { CSSProperties } from "react"

// Decorative, data-driven layout values (positions + per-line timing). Colors
// come from the .login-grid* classes in styles/index.css (token-derived).
const RUN_X: CSSProperties[] = [
  { top: "176px", width: "26vw", animationDuration: "4.5s" },
  { top: "396px", width: "18vw", animationDuration: "6s", animationDelay: "1.4s" },
  { bottom: "220px", width: "22vw", animationDuration: "7.5s", animationDelay: "3.2s" },
]
const RUN_Y: CSSProperties[] = [
  { left: "21%", height: "30vh", animationDuration: "6.5s", animationDelay: "0.6s" },
  { right: "18%", height: "24vh", animationDuration: "8s", animationDelay: "2.4s" },
]
const CELLS: CSSProperties[] = [
  { left: "13%", top: "220px", width: "44px", height: "44px", animationDuration: "5.5s" },
  { left: "27%", bottom: "168px", width: "44px", height: "44px", animationDuration: "7s", animationDelay: "1.6s" },
  { right: "15%", top: "300px", width: "88px", height: "44px", animationDuration: "8s", animationDelay: "3s" },
  { right: "24%", bottom: "260px", width: "44px", height: "44px", animationDuration: "6.5s", animationDelay: "4.2s" },
]

/** Drifting grid, sweeping light lines and glowing cells behind the auth card. */
export function LoginGrid() {
  return (
    <div className="login-grid" aria-hidden="true">
      <div className="login-grid__mesh" />
      <div className="login-grid__mesh login-grid__mesh--wide" />
      {RUN_X.map((style, i) => (
        <div key={`x${i}`} className="login-grid__runx" style={style} />
      ))}
      {RUN_Y.map((style, i) => (
        <div key={`y${i}`} className="login-grid__runy" style={style} />
      ))}
      {CELLS.map((style, i) => (
        <div key={`c${i}`} className="login-grid__cell" style={style} />
      ))}
      <div className="login-grid__veil" />
    </div>
  )
}
