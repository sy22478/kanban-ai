import type { Board, BoardDetail, Card, Column } from './types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    headers: init?.body ? { 'content-type': 'application/json' } : undefined,
    ...init,
  })

  if (!response.ok) {
    // Surfaced to the user rather than swallowed. A failed write that looks like
    // a success is the failure mode this whole project is trying to avoid.
    throw new Error(`${init?.method ?? 'GET'} ${path} failed with ${response.status}`)
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
