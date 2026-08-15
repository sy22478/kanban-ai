export type User = {
  id: string
  email: string
}

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

/** One thing the assistant did, described by the tool that did it rather than by
 *  the model. The distinction matters: the model's own account of its actions is
 *  precisely what cannot be trusted when it has been fed instructions from a
 *  card, so the panel shows these instead of taking the reply's word for it. */
export type AgentAction = {
  tool: string
  ok: boolean
  summary: string
}

export type AgentChatResponse = {
  reply: string
  actions: AgentAction[]
  /** Whether anything was written. The board is refetched only when this is
   *  true, so a question that changed nothing does not cost a round trip. */
  changed: boolean
}
