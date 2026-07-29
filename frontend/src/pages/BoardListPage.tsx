import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { api } from '../api'
import type { Board } from '../types'

export function BoardListPage() {
  const [boards, setBoards] = useState<Board[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [title, setTitle] = useState('')

  const refresh = () =>
    api
      .listBoards()
      .then((next) => {
        setBoards(next)
        setError(null)
      })
      .catch((cause: Error) => setError(cause.message))

  useEffect(() => {
    void refresh()
  }, [])

  const create = async (event: React.FormEvent) => {
    event.preventDefault()
    const next = title.trim()
    if (!next) return
    try {
      await api.createBoard(next)
      setTitle('')
      await refresh()
    } catch (cause) {
      setError((cause as Error).message)
    }
  }

  const remove = async (boardId: string) => {
    try {
      await api.deleteBoard(boardId)
      await refresh()
    } catch (cause) {
      setError((cause as Error).message)
    }
  }

  return (
    <main className="page">
      <div className="topbar">
        <h1>Boards</h1>
      </div>

      {error && <p className="error">Could not reach the API: {error}</p>}

      <form className="row" onSubmit={create} style={{ marginBottom: '1rem' }}>
        <input
          aria-label="New board title"
          placeholder="New board"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
        />
        <button type="submit" className="primary">
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
