import type { Board, BoardDetail, Card, Column } from './types'

type ValidationError = { loc?: unknown[]; msg?: string }

/** What the server said was wrong, not just that something was.
 *
 *  FastAPI reports a rejected body as `detail: [{loc, msg}, ...]` and an
 *  HTTPException as `detail: "some text"`, so both shapes are read. `loc[0]` is
 *  the part of the request ("body", "query"), which the user does not need, so
 *  it is dropped and the field name kept. `input` is deliberately ignored: it
 *  echoes the entire rejected value, which for an over-long title is the whole
 *  title. A stopped back-end returns a non-JSON body through the dev proxy,
 *  which is why the parse is allowed to fail.
 */
async function describe(response: Response): Promise<string> {
  const body = (await response.json().catch(() => null)) as { detail?: unknown } | null
  const detail = body?.detail

  if (typeof detail === 'string') return detail

  if (Array.isArray(detail)) {
    const reasons = (detail as ValidationError[])
      .map((item) => {
        const field = Array.isArray(item.loc) ? item.loc.slice(1).join('.') : ''
        return field ? `${field}: ${item.msg}` : item.msg
      })
      .filter(Boolean)

    if (reasons.length > 0) return reasons.join('; ')
  }

  return response.statusText || 'no detail given'
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    headers: init?.body ? { 'content-type': 'application/json' } : undefined,
    ...init,
  })

  if (!response.ok) {
    // Surfaced to the user rather than swallowed, with the server's reason
    // intact. A failed write that looks like a success is the failure mode this
    // whole project is trying to avoid; one that reports only a status code is
    // the same failure with a smaller blast radius.
    const reason = await describe(response)
    throw new Error(
      `${init?.method ?? 'GET'} ${path} failed with ${response.status}: ${reason}`,
    )
  }

  return response.status === 204 ? (undefined as T) : ((await response.json()) as T)
}

export const api = {
  listBoards: () => request<Board[]>('/boards'),

  createBoard: (title: string) =>
    request<Board>('/boards', { method: 'POST', body: JSON.stringify({ title }) }),

  getBoard: (boardId: string) => request<BoardDetail>(`/boards/${boardId}`),

  renameBoard: (boardId: string, title: string) =>
    request<Board>(`/boards/${boardId}`, {
      method: 'PATCH',
      body: JSON.stringify({ title }),
    }),

  deleteBoard: (boardId: string) =>
    request<void>(`/boards/${boardId}`, { method: 'DELETE' }),

  createColumn: (boardId: string, title: string) =>
    request<Column>(`/boards/${boardId}/columns`, {
      method: 'POST',
      body: JSON.stringify({ title }),
    }),

  renameColumn: (columnId: string, title: string) =>
    request<Column>(`/columns/${columnId}`, {
      method: 'PATCH',
      body: JSON.stringify({ title }),
    }),

  moveColumn: (columnId: string, position: number) =>
    request<Column>(`/columns/${columnId}/move`, {
      method: 'PATCH',
      body: JSON.stringify({ position }),
    }),

  deleteColumn: (columnId: string) =>
    request<void>(`/columns/${columnId}`, { method: 'DELETE' }),

  createCard: (columnId: string, title: string) =>
    request<Card>(`/columns/${columnId}/cards`, {
      method: 'POST',
      body: JSON.stringify({ title }),
    }),

  updateCard: (cardId: string, changes: { title?: string; description?: string | null }) =>
    request<Card>(`/cards/${cardId}`, {
      method: 'PATCH',
      body: JSON.stringify(changes),
    }),

  moveCard: (cardId: string, columnId: string, position: number) =>
    request<Card>(`/cards/${cardId}/move`, {
      method: 'PATCH',
      body: JSON.stringify({ column_id: columnId, position }),
    }),

  deleteCard: (cardId: string) =>
    request<void>(`/cards/${cardId}`, { method: 'DELETE' }),
}
