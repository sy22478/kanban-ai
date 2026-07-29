export type Card = {
  id: string
  column_id: string
  title: string
  description: string | null
  position: number
}

export type Column = {
  id: string
  board_id: string
  title: string
  position: number
  cards: Card[]
}

export type Board = {
  id: string
  title: string
  created_at: string
}

export type BoardDetail = Board & {
  columns: Column[]
}
