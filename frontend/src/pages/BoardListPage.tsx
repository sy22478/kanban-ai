import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { api } from '../api'
import type { Board } from '../types'

export function BoardListPage() {
  const [boards, setBoards] = useState<Board[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [title, setTitle] = useState('')

  const load = useCallback(async () => {
    setBoards(await api.listBoards())
  }, [])

  /** The only writer of `error`, the same shape BoardPage uses. A refetch never
   *  clears the message a failed action just set. */
  const run = useCallback(
    async (action?: () => Promise<unknown>) => {
      setError(null)
      let failure: string | null = null
      let acted = true

      try {
        await action?.()
      } catch (cause) {
        failure = (cause as Error).message
        acted = false
      }

      try {
        await load()
      } catch (cause) {
        failure ??= (cause as Error).message
      }

      setError(failure)
      return acted
    },
    [load],
  )

  useEffect(() => {
    void run()
  }, [run])

  const create = async (event: React.FormEvent) => {
    event.preventDefault()
    const next = title.trim()
    if (!next) return
    if (await run(() => api.createBoard(next))) setTitle('')
  }

  const remove = (boardId: string) => run(() => api.deleteBoard(boardId))

  return (
    <main className="page">
      <div className="topbar">
        <h1>Boards</h1>
      </div>

      {/* Only a failed first load is an unreachable API. A rejected create is
          the server saying exactly what was wrong with the title, and framing
          that as a connection problem would be a lie. */}
      {error && (
        <p className="error">
          {boards === null ? `Could not load your boards: ${error}` : error}
        </p>
      )}

      <form className="row" onSubmit={create} style={{ marginBottom: '1rem' }}>
        <input
          aria-label="New board title"
          placeholder="New board"
          maxLength={200}
          value={title}
          onChange={(event) => setTitle(event.target.value)}
        />
        <button type="submit" className="primary" disabled={title.trim() === ''}>
          Create board
        </button>
      </form>

      {boards === null && !error && <p>Loading...</p>}

      {boards !== null && boards.length === 0 && <p>No boards yet.</p>}

      {boards !== null && boards.length > 0 && (
        <ul className="board-list">
          {boards.map((board) => (
            <li key={board.id}>
              <Link to={`/boards/${board.id}`}>{board.title}</Link>
              <button
                type="button"
                className="link"
                aria-label={`Delete board ${board.title}`}
                onClick={() => remove(board.id)}
              >
                x
              </button>
            </li>
          ))}
        </ul>
      )}
    </main>
  )
}
