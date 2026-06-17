export interface QuestionOption {
  label: string
  description?: string
}

export interface Question {
  question: string
  header?: string
  options: QuestionOption[]
  multiple?: boolean // Allow selecting multiple choices
  custom?: boolean // Allow typing a custom "Other" answer (default: true)
}

export interface QuestionRequest {
  id: string
  session_id: string
  questions: Question[]
  tool?: { messageID: string; callID: string }
  created_at: string
}

export type QuestionAnswer = string[] // Selected labels for one question
