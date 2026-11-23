import { useId, type SelectHTMLAttributes } from "react"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/select"

interface SelectFieldProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "id"> {
  label: string
  error?: string
  hint?: string
}

export function SelectField({ label, error, hint, children, ...selectProps }: SelectFieldProps) {
  const id = useId()
  const messageId = error ? `${id}-error` : hint ? `${id}-hint` : undefined

  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <NativeSelect
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={messageId}
        {...selectProps}
      >
        {children}
      </NativeSelect>
      {error ? (
        <p id={messageId} role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : hint ? (
        <p id={messageId} className="text-sm text-muted-foreground">
          {hint}
        </p>
      ) : null}
    </div>
  )
}