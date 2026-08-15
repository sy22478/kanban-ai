import { useEffect, useRef, useState } from 'react'

import { api, readable } from '../api'
import type { AgentAction } from '../types'

type Entry =
  | { kind: 'you'; text: string }
  | { kind: 'assistant'; text: string; actions: AgentAction[] }
  | { kind: 'error'; text: string }

/** The chat, scoped to one board.
 *
 *  It keeps its own transcript and its own errors rather than going through the
 *  board page's `run`, which is the single writer of that page's error line.
 *  Sharing it would mean a failed assistant turn and a failed drag both write to
 *  the same place and quietly overwrite each other.
 *
 *  The transcript is deliberately not persisted. Nothing on the server stores it,
 *  so a reload starts a fresh conversation, and pretending otherwise by keeping
 *  it in localStorage would show a history the model does not actually have. */
export function AssistantPanel({
  boardId,
  onChanged,
}: {
  boardId: string
  /** Refetch the board. Called only when the server says something was written. */
  onChanged: () => Promise<unknown>
}) {
  const [entries, setEntries] = useState<Entry[]>([])
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const transcript = useRef<HTMLDivElement>(null)

  useEffect(() => {
    // Keep the newest turn in view. The transcript grows downward and a reply
    // that arrives below the fold reads as nothing having happened.
    transcript.current?.scrollTo({ top: transcript.current.scrollHeight })
  }, [entries])

  const add = (entry: Entry) => setEntries((previous) => [...previous, entry])

  async function send(event: React.FormEvent) {
    event.preventDefault()
    const text = message.trim()
    if (!text || busy) return

    // Into the transcript before the request, so the input can be cleared
    // without losing what was asked if the turn then fails.
    add({ kind: 'you', text })
    setMessage('')
    setBusy(true)

    try {
      const answer = await api.chat(boardId, text)
      add({ kind: 'assistant', text: answer.reply, actions: answer.actions })
      // Only when the server says so. A turn that answered a question without
      // writing anything does not need the board refetched.
      if (answer.changed) await onChanged()
    } catch (cause) {
      // A 502 from a model that died before acting means nothing was written, so
      // there is nothing to refetch. A model that died after acting does not
      // arrive here at all: the server reports that turn as a normal outcome
      // with its actions listed, precisely so those writes are not lost.
      add({ kind: 'error', text: readable(cause) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="assistant" aria-label="Assistant">
      <h2>Assistant</h2>

      <div className="transcript" ref={transcript} aria-live="polite">
        {entries.length === 0 && (
          <p className="empty">
            Ask for a change to this board. For example: add a card called Write
            the README to To Do.
          </p>
        )}

        {entries.map((entry, index) => (
          <div key={index} className={`turn ${entry.kind}`}>
            <span className="who">
              {entry.kind === 'you' ? 'You' : entry.kind === 'error' ? 'Failed' : 'Assistant'}
            </span>
            <p>{entry.text}</p>

            {/* What the tools reported doing, not what the reply claims. If the
                model is talked into an action nobody asked for, it shows up
                here even when the sentence above does not mention it. */}
            {entry.kind === 'assistant' && entry.actions.length > 0 && (
              <ul className="actions">
                {entry.actions.map((action, position) => (
                  <li key={position} className={action.ok ? 'did' : 'refused'}>
                    {action.summary}
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>

      <form className="row" onSubmit={send}>
        <input
          aria-label="Message the assistant"
          placeholder={busy ? 'Thinking...' : 'Ask for a change'}
          // Agrees with AgentChatRequest's cap, so that 422 is unreachable here.
          maxLength={2000}
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          disabled={busy}
        />
        <button type="submit" className="primary" disabled={busy || message.trim() === ''}>
          Send
        </button>
      </form>
    </section>
  )
}
