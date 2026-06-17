import { useState } from "react"
import { HelpCircle, Send, X } from "lucide-react"
import { useQuestionStore } from "@/stores/question"
import { api } from "@/services/api"
import type { QuestionRequest } from "@/types"

interface QuestionCardProps {
  request: QuestionRequest
}

export function QuestionCard({ request }: QuestionCardProps) {
  // Per-question selected labels: answers[questionIndex] = string[]
  const [selected, setSelected] = useState<string[][]>(
    () => request.questions.map(() => [])
  )
  const [customInputs, setCustomInputs] = useState<Record<number, string>>({})
  const [loading, setLoading] = useState(false)
  const [dismissing, setDismissing] = useState(false)
  const removePending = useQuestionStore((s) => s.removePending)

  const toggleOption = (qi: number, label: string) => {
    setSelected((prev) => {
      const updated = [...prev]
      const q = request.questions[qi]
      if (q.multiple) {
        // Multi-select: toggle in/out
        const current = updated[qi] || []
        updated[qi] = current.includes(label)
          ? current.filter((v) => v !== label)
          : [...current, label]
      } else {
        // Single-select: replace
        updated[qi] = [label]
      }
      return updated
    })
  }

  const handleDismiss = () => {
    setDismissing(true)
    try {
      api.rejectQuestion(request.id)
      removePending(request.id)
    } catch (e) {
      console.error("Failed to dismiss question:", e)
    } finally {
      setDismissing(false)
    }
  }

  const handleSubmit = () => {
    setLoading(true)
    try {
      // Build final answers: replace __other__ with custom text
      const finalAnswers: string[][] = request.questions.map((_q, qi) => {
        const sel = selected[qi] || []
        return sel.map((v) => v === "__other__" ? customInputs[qi] || "" : v)
      })
      api.replyQuestion(request.id, finalAnswers)
      removePending(request.id)
    } catch (e) {
      console.error("Failed to reply question:", e)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="border-t border-[hsl(var(--border))]/50 bg-[hsl(var(--card))] p-4">
      <div className="max-w-2xl mx-auto rounded-sm border border-[hsl(var(--primary))]/20 bg-[hsl(var(--primary))]/5 overflow-hidden animate-slide-up">
        <div className="flex items-center gap-2.5 px-4 py-3 border-b border-[hsl(var(--border))]/50 bg-[hsl(var(--primary))]/5">
          <div className="h-7 w-7 rounded-sm bg-[hsl(var(--primary))]/15 flex items-center justify-center glow-cyan">
            <HelpCircle className="h-3.5 w-3.5 text-[hsl(var(--primary))]" />
          </div>
          <span className="text-sm font-display uppercase tracking-wider">Agent is asking you a question</span>
        </div>
        <div className="p-4 space-y-4">
          {request.questions.map((q, qi) => {
            const sel = selected[qi] || []
            return (
              <div key={qi} className="space-y-2.5">
                <p className="text-sm font-display uppercase tracking-wider">{q.question}</p>
                <div className="space-y-1.5">
                  {q.options.map((opt, oi) => {
                    const isChecked = sel.includes(opt.label)
                    return (
                      <label
                        key={oi}
                        className={`flex items-start gap-2.5 px-3.5 py-2.5 rounded-sm border transition-all cursor-pointer ${
                          isChecked
                            ? "border-[hsl(var(--primary))]/30 bg-[hsl(var(--primary))]/5 glow-cyan"
                            : "border-[hsl(var(--border))]/50 hover:bg-[hsl(var(--muted))]/50 hover:border-[hsl(var(--border))]"
                        }`}
                      >
                        <input
                          type={q.multiple ? "checkbox" : "radio"}
                          name={`q${qi}`}
                          value={opt.label}
                          checked={isChecked}
                          onChange={() => toggleOption(qi, opt.label)}
                          className="mt-0.5"
                        />
                        <div>
                          <div className="text-sm font-mono font-medium">{opt.label}</div>
                          {opt.description && (
                            <div className="text-xs text-[hsl(var(--muted-foreground))] mt-0.5">{opt.description}</div>
                          )}
                        </div>
                      </label>
                    )
                  })}
                  {(q.custom !== false) && (() => {
                    const otherChecked = sel.includes("__other__")
                    return (
                      <label className={`flex items-start gap-2.5 px-3.5 py-2.5 rounded-sm border transition-all cursor-pointer ${
                        otherChecked
                          ? "border-[hsl(var(--primary))]/30 bg-[hsl(var(--primary))]/5 glow-cyan"
                          : "border-[hsl(var(--border))]/50 hover:bg-[hsl(var(--muted))]/50 hover:border-[hsl(var(--border))]"
                      }`}>
                        <input
                          type={q.multiple ? "checkbox" : "radio"}
                          name={`q${qi}`}
                          value="__other__"
                          checked={otherChecked}
                          onChange={() => toggleOption(qi, "__other__")}
                          className="mt-0.5"
                        />
                        <div className="flex-1">
                          <div className="text-sm font-mono font-medium">Other</div>
                          {otherChecked && (
                            <input
                              type="text"
                              value={customInputs[qi] || ""}
                              onChange={(e) => setCustomInputs({ ...customInputs, [qi]: e.target.value })}
                              placeholder="Type your answer..."
                              className="mt-1.5 w-full px-3 py-1.5 text-sm font-mono rounded-sm border border-[hsl(var(--border))]/50 bg-[hsl(var(--surface-1))] focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary))]/20 focus:border-[hsl(var(--primary))]/30 transition-all"
                              autoFocus
                            />
                          )}
                        </div>
                      </label>
                    )
                  })()}
                </div>
              </div>
            )
          })}
        </div>
        <div className="flex justify-between px-4 py-3 border-t border-[hsl(var(--border))]/50 bg-[hsl(var(--muted))]/20">
          <button
            onClick={handleDismiss}
            disabled={dismissing || loading}
            className="flex items-center gap-2 px-4 py-2 text-sm font-mono uppercase tracking-wider rounded-sm border border-[hsl(var(--border))]/50 hover:bg-[hsl(var(--muted))] hover:border-[hsl(var(--border))] transition-all cursor-pointer disabled:opacity-50"
          >
            <X className="h-3.5 w-3.5" />
            Dismiss
          </button>
          <button
            onClick={handleSubmit}
            disabled={loading || dismissing}
            className="flex items-center gap-2 px-4 py-2 text-sm font-mono uppercase tracking-wider rounded-sm bg-[hsl(var(--cta))] text-[hsl(var(--cta-foreground))] hover:opacity-90 transition-opacity cursor-pointer disabled:opacity-50 glow-cyan"
          >
            <Send className="h-3.5 w-3.5" />
            Submit
          </button>
        </div>
      </div>
    </div>
  )
}
