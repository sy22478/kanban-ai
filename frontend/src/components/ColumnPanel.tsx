import { useDroppable } from '@dnd-kit/core'
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { useState } from 'react'

import type { Column } from '../types'
import { CardItem } from './CardItem'
import { InlineEdit } from './InlineEdit'

type Props = {
  column: Column
  index: number
  count: number
  onRenameColumn: (columnId: string, title: string) => void
  onMoveColumn: (columnId: string, position: number) => void
  onDeleteColumn: (columnId: string) => void
  /** Resolves true when the card was actually created, so the typed title
   *  survives a rejected write. */
  onAddCard: (columnId: string, title: string) => Promise<boolean>
  onRenameCard: (cardId: string, title: string) => void
  onDeleteCard: (cardId: string) => void
}

export function ColumnPanel({
  column,
  index,
  count,
  onRenameColumn,
  onMoveColumn,
  onDeleteColumn,
  onAddCard,
  onRenameCard,
  onDeleteCard,
}: Props) {
  const [title, setTitle] = useState('')

  // The column itself is a drop target, so a card can be dropped into a column
  // that has no cards to drop onto.
  const { setNodeRef, isOver } = useDroppable({ id: column.id })

  return (
    <section className={isOver ? 'column over' : 'column'} data-column={column.title}>
      <header className="column-head">
        <h2>
          <InlineEdit
            value={column.title}
            label={`column ${column.title}`}
            onSubmit={(next) => onRenameColumn(column.id, next)}
          />
        </h2>
        <span className="count">{column.cards.length}</span>
        {/* Reorder by button rather than by dragging the column. The card drag
            path is the one part of the board that needs a human to verify, so it
            is left alone; these are clickable, keyboard reachable, and hit the
            same PATCH /api/columns/{id}/move the drag would have. */}
        <button
          type="button"
          className="link"
          aria-label={`Move column ${column.title} left`}
          disabled={index === 0}
          onClick={() => onMoveColumn(column.id, index - 1)}
        >
          &lt;
        </button>
        <button
          type="button"
          className="link"
          aria-label={`Move column ${column.title} right`}
          disabled={index === count - 1}
          onClick={() => onMoveColumn(column.id, index + 1)}
        >
          &gt;
        </button>
        <button
          type="button"
          className="link"
          aria-label={`Delete column ${column.title}`}
          onClick={() => onDeleteColumn(column.id)}
        >
          x
        </button>
      </header>

      <div className="cards" ref={setNodeRef}>
        <SortableContext
          items={column.cards.map((card) => card.id)}
          strategy={verticalListSortingStrategy}
        >
          {column.cards.map((card) => (
            <CardItem
              key={card.id}
              card={card}
              onRename={onRenameCard}
              onDelete={onDeleteCard}
            />
          ))}
        </SortableContext>
        {column.cards.length === 0 && <p className="empty">No cards</p>}
      </div>

      <form
        className="row"
        onSubmit={async (event) => {
          event.preventDefault()
          const next = title.trim()
          if (!next) return
          if (await onAddCard(column.id, next)) setTitle('')
        }}
      >
        <input
          aria-label={`New card in ${column.title}`}
          placeholder="Add a card"
          maxLength={200}
          value={title}
          onChange={(event) => setTitle(event.target.value)}
        />
        <button type="submit" disabled={title.trim() === ''}>
          Add
        </button>
      </form>
    </section>
  )
}
