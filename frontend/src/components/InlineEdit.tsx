import { useState } from 'react'

type Props = {
  value: string
  label: string
  onSubmit: (next: string) => void
}

/** Click the text to edit it. Enter commits, Escape abandons. */
export function InlineEdit({ value, label, onSubmit }: Props) {
  const [draft, setDraft] = useState<string | null>(null)

  if (draft === null) {
    return (
      <button
        type="button"
        className="inline-view"
        aria-label={`Rename ${label}`}
        onClick={() => setDraft(value)}
      >
        {value}
      </button>
    )
  }

  const commit = () => {
    const next = draft.trim()
    setDraft(null)
    if (next && next !== value) {
      onSubmit(next)
    }
  }

  return (
    <form
      className="inline-edit"
      onSubmit={(event) => {
        event.preventDefault()
        commit()
      }}
    >
      {/* required: Enter on an empty field is refused by the browser with a
          reason, instead of silently reverting to the old name. Clicking away
          still abandons the edit, which is what Escape means too.
          maxLength: agrees with the 200 character cap every title schema has. */}
      <input
        autoFocus
        required
        maxLength={200}
        aria-label={`New name for ${label}`}
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === 'Escape') setDraft(null)
        }}
      />
    </form>
  )
}
