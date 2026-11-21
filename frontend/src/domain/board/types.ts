/** Plain data shapes the domain is built from (camelCase, real Dates). No framework here. */
import type { ActivityKind, BoardRole, LabelColor } from '../../api/dtos'

export type { ActivityKind, BoardRole, LabelColor }

export interface CardData {
  id: number
  boardId: number
  listId: number
  version: number
  title: string
  description: string | null
  position: number
  dueAt: Date | null
  completedAt: Date | null
  archivedAt: Date | null
  labelIds: number[]
  assigneeIds: number[]
  checklistDone: number
  checklistTotal: number
  commentCount: number
  /** Only present when the card was loaded on its own (GET /api/cards/{id}). */
  checklist?: ChecklistItem[]
}

export interface ChecklistItem {
  id: number
  text: string
  doneAt: Date | null
}

export interface ListData {
  id: number
  name: string
  isDone: boolean
  cards: CardData[]
}

export interface Member {
  userId: number
  displayName: string
  email: string
  role: BoardRole
}

export interface Label {
  id: number
  name: string
  color: LabelColor
}

export interface BoardData {
  id: number
  name: string
  description: string | null
  myRole: BoardRole
  lists: ListData[]
  members: Member[]
  labels: Label[]
}

export interface BoardSummary {
  id: number
  name: string
  description: string | null
  myRole: BoardRole
}

export interface Comment {
  id: number
  author: { id: number; displayName: string } | null
  body: string
  createdAt: Date
  editedAt: Date | null
}

export interface ActivityEntry {
  id: number
  boardId: number
  cardId: number | null
  actor: { id: number; displayName: string } | null
  kind: ActivityKind
  data: Record<string, unknown>
  createdAt: Date
}

export interface CardSearchHit extends CardData {
  boardName: string
  listName: string
}

/** What a card PATCH may change (camelCase; the repository converts). */
export interface CardChanges {
  title?: string
  description?: string | null
  dueAt?: Date | null
  completed?: boolean
  archived?: boolean
}
