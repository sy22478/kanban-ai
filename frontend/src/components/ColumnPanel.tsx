import { useDroppable } from '@dnd-kit/core'
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { useState } from 'react'

import type { Column } from '../types'
import { CardItem } from './CardItem'
import { InlineEdit } from './InlineEdit'

type Props = {
  column: Column
  onRenameColumn: (columnId: string, title: string) => void
  onDeleteColumn: (columnId: string) => void
  onAddCard: (columnId: string, title: string) => void
  onRenameCard: (cardId: string, title: string) => void
  onDeleteCard: (cardId: string) => void
}

export function ColumnPanel({
  column,
  onRenameColumn,
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
        onSubmit={(event) => {
          event.preventDefault()
          const next = title.trim()
          if (!next) return
          onAddCard(column.id, next)
          setTitle('')
        }}
      >
        <input
          aria-label={`New card in ${column.title}`}
          placeholder="Add a card"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
        />
        <button type="submit">Add</button>
      </form>
    </section>
  )
}
