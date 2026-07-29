import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'

import type { Card } from '../types'
import { InlineEdit } from './InlineEdit'

type Props = {
  card: Card
  onRename: (cardId: string, title: string) => void
  onDelete: (cardId: string) => void
}

export function CardItem({ card, onRename, onDelete }: Props) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: card.id })

  return (
    <div
      ref={setNodeRef}
      className={isDragging ? 'card dragging' : 'card'}
      style={{ transform: CSS.Translate.toString(transform), transition }}
      data-card-title={card.title}
    >
      {/* The handle carries the listeners, not the whole card, so the title
          stays clickable for renaming. */}
      <span
        className="grip"
        aria-label={`Drag ${card.title}`}
        {...attributes}
        {...listeners}
      >
        ::
      </span>
      <span className="title">
        <InlineEdit
          value={card.title}
          label={`card ${card.title}`}
          onSubmit={(title) => onRename(card.id, title)}
        />
      </span>
      <button
        type="button"
        className="link"
        aria-label={`Delete card ${card.title}`}
        onClick={() => onDelete(card.id)}
      >
        x
      </button>
    </div>
  )
}
