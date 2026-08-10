import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  closestCorners,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from '@dnd-kit/core'
import { sortableKeyboardCoordinates } from '@dnd-kit/sortable'
import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { api } from '../api'
import { SignOutButton } from '../auth'
import { ColumnPanel } from '../components/ColumnPanel'
import { InlineEdit } from '../components/InlineEdit'
import type { BoardDetail, Card } from '../types'

function locate(board: BoardDetail, cardId: string) {
  for (const column of board.columns) {
    const index = column.cards.findIndex((card) => card.id === cardId)
    if (index !== -1) return { column, index }
  }
  return null
}

/** The same rearrangement the server performs, applied locally so the board does
 *  not wait for a round trip. The server remains the authority: if its answer
 *  differs, the refetch below replaces this. */
function applyMove(
  board: BoardDetail,
  cardId: string,
  toColumnId: string,
  toIndex: number,
): BoardDetail {
  const next = structuredClone(board)
  const from = locate(next, cardId)
  if (!from) return board

  const [card] = from.column.cards.splice(from.index, 1)
  const target = next.columns.find((column) => column.id === toColumnId)
  if (!target) return board

  card.column_id = toColumnId
  target.cards.splice(Math.max(0, Math.min(toIndex, target.cards.length)), 0, card)

  for (const column of next.columns) {
    column.cards.forEach((each, index) => {
      each.position = index
    })
  }
  return next
}

export function BoardPage() {
  const { boardId } = useParams<{ boardId: string }>()
  const [board, setBoard] = useState<BoardDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [dragging, setDragging] = useState<Card | null>(null)
  const [columnTitle, setColumnTitle] = useState('')

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  /** Fetches, and throws if it cannot. It does not touch `error`: see run(). */
  const load = useCallback(async () => {
    if (!boardId) return
    setBoard(await api.getBoard(boardId))
  }, [boardId])

  /** The only writer of `error`, which is why load() above does not touch it.
   *  Two writers is what hid every failed write on this page: the refetch that
   *  follows a failed action succeeded, and cleared the message explaining the
   *  failure before it had been on screen for a frame.
   *
   *  Every write goes through here, and so does the initial load. The error
   *  clears when an action starts, not when a refetch succeeds. */
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

      // Refetch either way, so a failed write cannot leave the board showing
      // something that never happened. If both fail, which is what a stopped
      // back-end looks like, the action's error wins: it names what the user
      // was actually trying to do.
      try {
        await load()
      } catch (cause) {
        failure ??= (cause as Error).message
      }

      setError(failure)
      // Whether the write landed, so a caller can keep the user's typed text on
      // screen when it did not. An error saying the title is too long is no use
      // if the input it refers to has already been cleared.
      return acted
    },
    [load],
  )

  useEffect(() => {
    void run()
  }, [run])

  const onDragStart = (event: DragStartEvent) => {
    if (!board) return
    const found = locate(board, String(event.active.id))
    setDragging(found ? found.column.cards[found.index] : null)
  }

  const onDragEnd = (event: DragEndEvent) => {
    setDragging(null)
    const { active, over } = event
    if (!board || !over) return

    const cardId = String(active.id)
    const from = locate(board, cardId)
    if (!from) return

    const overId = String(over.id)
    const overColumn = board.columns.find((column) => column.id === overId)
    const overCard = overColumn ? null : locate(board, overId)

    const toColumnId = overColumn ? overColumn.id : overCard?.column.id
    if (!toColumnId) return
    const toIndex = overColumn ? overColumn.cards.length : (overCard?.index ?? 0)

    if (from.column.id === toColumnId && from.index === toIndex) return

    setBoard(applyMove(board, cardId, toColumnId, toIndex))
    void run(() => api.moveCard(cardId, toColumnId, toIndex))
  }

  if (error && board === null) {
    return (
      <main className="page">
        <div className="topbar">
          <Link to="/">Boards</Link>
        </div>
        <p className="error">Could not load the board: {error}</p>
      </main>
    )
  }

  if (!board) {
    return (
      <main className="page">
        <p>Loading...</p>
      </main>
    )
  }

  return (
    <main className="page">
      <div className="topbar">
        <Link to="/">Boards</Link>
        <h1>
          <InlineEdit
            value={board.title}
            label={`board ${board.title}`}
            onSubmit={(title) => run(() => api.renameBoard(board.id, title))}
          />
        </h1>
        <form
          className="row"
          onSubmit={async (event) => {
            event.preventDefault()
            const next = columnTitle.trim()
            if (!next) return
            if (await run(() => api.createColumn(board.id, next))) setColumnTitle('')
          }}
        >
          <input
            aria-label="New column title"
            placeholder="Add a column"
            // Agrees with ColumnCreate's cap, so the 422 is unreachable from here.
            maxLength={200}
            value={columnTitle}
            onChange={(event) => setColumnTitle(event.target.value)}
          />
          {/* Disabled rather than silently doing nothing when there is no title.
              It also stops the form submitting on Enter, so both routes to an
              empty title give the same visible answer. */}
          <button type="submit" disabled={columnTitle.trim() === ''}>
            Add column
          </button>
        </form>
        <SignOutButton />
      </div>

      {error && <p className="error">{error}</p>}

      <DndContext
        sensors={sensors}
        collisionDetection={closestCorners}
        onDragStart={onDragStart}
        onDragEnd={onDragEnd}
      >
        <div className="board">
          {board.columns.map((column, index) => (
            <ColumnPanel
              key={column.id}
              column={column}
              index={index}
              count={board.columns.length}
              onRenameColumn={(columnId, title) =>
                run(() => api.renameColumn(columnId, title))
              }
              onMoveColumn={(columnId, position) =>
                run(() => api.moveColumn(columnId, position))
              }
              onDeleteColumn={(columnId) => run(() => api.deleteColumn(columnId))}
              onAddCard={(columnId, title) => run(() => api.createCard(columnId, title))}
              onRenameCard={(cardId, title) =>
                run(() => api.updateCard(cardId, { title }))
              }
              onDeleteCard={(cardId) => run(() => api.deleteCard(cardId))}
            />
          ))}
          {board.columns.length === 0 && <p>No columns yet.</p>}
        </div>

        <DragOverlay>
          {dragging && <div className="card-overlay">{dragging.title}</div>}
        </DragOverlay>
      </DndContext>
    </main>
  )
}
