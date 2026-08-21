import { LandingTopbar } from "./LandingTopbar"
import { LandingHero } from "./LandingHero"
import { LandingMock } from "./LandingMock"
import { LandingFeatures } from "./LandingFeatures"
import { LandingFlow } from "./LandingFlow"
import { LandingOutro } from "./LandingOutro"

export default function LandingRoute() {
  return (
    <div className="scr flex min-h-screen flex-col overflow-x-hidden bg-bg text-ink">
      <LandingTopbar />
      <main className="flex-1">
        <LandingHero />
        <LandingMock />
        <LandingFeatures />
        <LandingFlow />
        <LandingOutro />
      </main>
    </div>
  )
}
