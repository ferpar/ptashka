/** DTO (wire, snake_case, ISO strings) → domain data (camelCase, Dates). Pure functions. */
import type {
  ActivityDTO,
  BoardDetailDTO,
  BoardSummaryDTO,
  CardDTO,
  CardDetailDTO,
  CardSearchHitDTO,
  ChecklistItemDTO,
  CommentDTO,
} from '../../api/dtos'
import type { ActivityEntry, BoardData, BoardSummary, CardData, CardSearchHit, ChecklistItem, Comment } from './types'

const date = (iso: string): Date => new Date(iso)
const maybeDate = (iso: string | null | undefined): Date | null => (iso ? new Date(iso) : null)

export const toChecklistItem = (dto: ChecklistItemDTO): ChecklistItem => ({
  id: dto.id,
  text: dto.text,
  doneAt: maybeDate(dto.done_at),
})

export function toCardData(dto: CardDTO | CardDetailDTO): CardData {
  const data: CardData = {
    id: dto.id,
    boardId: dto.board_id,
    listId: dto.list_id,
    version: dto.version,
    title: dto.title,
    description: dto.description ?? null,
    position: dto.position,
    dueAt: maybeDate(dto.due_at),
    completedAt: maybeDate(dto.completed_at),
    archivedAt: maybeDate(dto.archived_at),
    labelIds: dto.label_ids,
    assigneeIds: dto.assignee_ids,
    checklistDone: dto.checklist_done,
    checklistTotal: dto.checklist_total,
    commentCount: dto.comment_count,
  }
  if ('checklist' in dto) data.checklist = dto.checklist.map(toChecklistItem)
  return data
}

export const toBoardSummary = (dto: BoardSummaryDTO): BoardSummary => ({
  id: dto.id,
  name: dto.name,
  description: dto.description ?? null,
  myRole: dto.my_role,
})

export const toBoardData = (dto: BoardDetailDTO): BoardData => ({
  id: dto.id,
  name: dto.name,
  description: dto.description ?? null,
  myRole: dto.my_role,
  lists: dto.lists.map((l) => ({ id: l.id, name: l.name, isDone: l.is_done, cards: l.cards.map(toCardData) })),
  members: dto.members.map((m) => ({ userId: m.user.id, displayName: m.user.display_name, email: m.user.email, role: m.role })),
  labels: dto.labels.map((l) => ({ id: l.id, name: l.name, color: l.color })),
})

const toPerson = (u: { id: number; display_name: string } | null | undefined) =>
  u ? { id: u.id, displayName: u.display_name } : null

export const toComment = (dto: CommentDTO): Comment => ({
  id: dto.id,
  author: toPerson(dto.author),
  body: dto.body,
  createdAt: date(dto.created_at),
  editedAt: maybeDate(dto.edited_at),
})

export const toActivity = (dto: ActivityDTO): ActivityEntry => ({
  id: dto.id,
  boardId: dto.board_id,
  cardId: dto.card_id ?? null,
  actor: toPerson(dto.actor),
  kind: dto.kind,
  data: dto.data,
  createdAt: date(dto.created_at),
})

export const toSearchHit = (dto: CardSearchHitDTO): CardSearchHit => ({
  ...toCardData(dto),
  boardName: dto.board_name,
  listName: dto.list_name,
})
