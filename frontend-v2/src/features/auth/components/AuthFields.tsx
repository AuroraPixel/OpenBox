import { useId, useState } from "react"
import { useTranslation } from "react-i18next"

const FIELD =
  "h-10.5 w-full box-border rounded-lg border border-hair bg-card px-3.5 text-md text-ink outline-none placeholder:text-n500 focus:border-n400"

interface TextFieldProps {
  label: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
  type?: "text" | "email"
  autoComplete?: string
}

export function TextField({ label, value, onChange, placeholder, type = "text", autoComplete }: TextFieldProps) {
  const id = useId()
  return (
    <div className="mt-3.5 flex flex-col gap-1.5 first:mt-0">
      <label htmlFor={id} className="text-xs text-n700">
        {label}
      </label>
      <input
        id={id}
        type={type}
        value={value}
        autoComplete={autoComplete}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={FIELD}
      />
    </div>
  )
}

interface PasswordFieldProps {
  label: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
  autoComplete?: string
}

export function PasswordField({ label, value, onChange, placeholder, autoComplete }: PasswordFieldProps) {
  const id = useId()
  const [show, setShow] = useState(false)
  const { t } = useTranslation("auth")
  return (
    <div className="mt-3.5 flex flex-col gap-1.5">
      <label htmlFor={id} className="text-xs text-n700">
        {label}
      </label>
      <div className="relative flex items-center">
        <input
          id={id}
          type={show ? "text" : "password"}
          value={value}
          autoComplete={autoComplete}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className={`${FIELD} pe-16`}
        />
        <button
          type="button"
          onClick={() => setShow((s) => !s)}
          className="absolute end-3.5 text-2xs text-n600 hover:text-ink"
        >
          {show ? t("hide") : t("show")}
        </button>
      </div>
    </div>
  )
}
