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

  const refresh = useCallback(async () => {
    if (!boardId) return
    try {
      setBoard(await api.getBoard(boardId))
      setError(null)
    } catch (cause) {
      setError((cause as Error).message)
    }
  }, [boardId])

  useEffect(() => {
    void refresh()
  }, [refresh])

  /** Every write goes through here: act, then refetch. A failed write shows the
   *  error and restores the server's version rather than leaving the screen
   *  showing something that never happened. */
  const run = async (action: () => Promise<unknown>) => {
    try {
      await action()
      await refresh()
    } catch (cause) {
      setError((cause as Error).message)
      await refresh()
    }
  }

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
          onSubmit={(event) => {
            event.preventDefault()
            const next = columnTitle.trim()
            if (!next) return
            setColumnTitle('')
            void run(() => api.createColumn(board.id, next))
          }}
        >
          <input
            aria-label="New column title"
            placeholder="Add a column"
            value={columnTitle}
            onChange={(event) => setColumnTitle(event.target.value)}
          />
          <button type="submit">Add column</button>
        </form>
      </div>

      {error && <p className="error">{error}</p>}

      <DndContext
        sensors={sensors}
        collisionDetection={closestCorners}
        onDragStart={onDragStart}
        onDragEnd={onDragEnd}
      >
        <div className="board">
          {board.columns.map((column) => (
            <ColumnPanel
              key={column.id}
              column={column}
              onRenameColumn={(columnId, title) =>
                run(() => api.renameColumn(columnId, title))
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
