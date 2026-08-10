import type { Board, BoardDetail, Card, Column, User } from './types'

type ValidationError = { loc?: unknown[]; msg?: string }

/** The header the back-end's CSRF middleware requires on every state-changing
 *  request. Its value is never read, only its presence: a cross-site <form>
 *  cannot set a header at all, and a cross-site fetch that sets one is turned
 *  into a preflight the API does not answer. See backend/app/csrf.py. */
const CSRF_HEADER = 'X-Kanban-CSRF'

/** A failure with the status still attached.
 *
 *  The guard needs to tell "your session ended" from "the title was too long",
 *  and the only thing that distinguishes them is the number. Reading it back out
 *  of the message text would make the message unchangeable: reword the string
 *  and the guard silently stops firing. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    /** The server's reason on its own, with no method or path in front of it.
     *  The sign-in and registration forms show this rather than `message`:
     *  "That email address is already registered" is something a person can act
     *  on, "POST /auth/register failed with 409: ..." is not. */
    readonly detail: string,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

/** The reason alone when the server gave one, the raw failure otherwise. A
 *  stopped back-end never becomes an ApiError, so its message is all there is. */
export function readable(cause: unknown): string {
  return cause instanceof ApiError ? cause.detail : (cause as Error).message
}

/** Called when the server says the caller is not signed in.
 *
 *  api.ts cannot navigate; it has no router. So it reports, and the auth
 *  provider decides, which keeps the redirect in one place instead of repeated
 *  at every call site that might get a 401. */
let onUnauthorized: (() => void) | null = null

export function setUnauthorizedHandler(handler: (() => void) | null) {
  onUnauthorized = handler
}

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

async function request<T>(
  path: string,
  init?: RequestInit,
  // Login answers 401 for a wrong password. That is the endpoint working, not a
  // session ending, so it must not trip the redirect: the user would be thrown
  // back to a fresh login page with the message about what they typed wrong
  // discarded.
  options?: { ownsUnauthorized?: boolean },
): Promise<T> {
  const method = init?.method ?? 'GET'

  // Built from init.headers rather than replacing it, because `...init` used to
  // be spread after `headers` and would have overwritten this object outright
  // the first time a caller passed one.
  const headers = new Headers(init?.headers)
  if (init?.body) headers.set('content-type', 'application/json')
  // Gated on the method, not on the body. deleteBoard, deleteColumn and
  // deleteCard send DELETE with no body; keying this off `init.body` would leave
  // all three without the header, and every delete in the app would be a 403.
  if (method !== 'GET') headers.set(CSRF_HEADER, '1')

  const response = await fetch(`/api${path}`, { ...init, headers })

  if (!response.ok) {
    // Surfaced to the user rather than swallowed, with the server's reason
    // intact. A failed write that looks like a success is the failure mode this
    // whole project is trying to avoid; one that reports only a status code is
    // the same failure with a smaller blast radius.
    const reason = await describe(response)

    if (response.status === 401 && !options?.ownsUnauthorized) onUnauthorized?.()

    throw new ApiError(
      response.status,
      reason,
      `${method} ${path} failed with ${response.status}: ${reason}`,
    )
  }

  return response.status === 204 ? (undefined as T) : ((await response.json()) as T)
}

export const api = {
  /** Who the caller is, or 401. The session cookie is HttpOnly, so this request
   *  is the only way the front-end can know whether it is signed in; JavaScript
   *  cannot look at the cookie. Its own 401 is the expected answer for a signed-
   *  out visitor and is handled by the caller, not by the redirect handler. */
  me: () => request<User>('/me', undefined, { ownsUnauthorized: true }),

  register: (email: string, password: string) =>
    // Exactly these two fields: RegisterRequest is strict and rejects extras.
    request<User>('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  login: (email: string, password: string) =>
    request<User>(
      '/auth/login',
      { method: 'POST', body: JSON.stringify({ email, password }) },
      { ownsUnauthorized: true },
    ),

  logout: () => request<void>('/auth/logout', { method: 'POST' }),

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
