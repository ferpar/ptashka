import type {
  ActivityPageDTO,
  BoardDetailDTO,
  BoardRole,
  BoardSummaryDTO,
  CardDetailDTO,
  CardSearchResponseDTO,
  CommentDTO,
  LabelColor,
  LabelDTO,
  ListDTO,
} from '../../api/dtos'
import type { HttpClient } from '../../api/http'
import type { BoardRepository, CardSearch } from './BoardRepository'
import { toActivity, toBoardData, toBoardSummary, toCardData, toComment, toSearchHit } from './mappers'
import type { CardChanges } from './types'

/** BoardRepository over the REST API. The only place that knows URLs and wire formats. */
export class HttpBoardRepository implements BoardRepository {
  constructor(private readonly http: HttpClient) {}

  async listBoards() {
    const { boards } = await this.http.get<{ boards: BoardSummaryDTO[] }>('/api/boards')
    return boards.map(toBoardSummary)
  }
  async createBoard(name: string, description: string | null) {
    return toBoardData(await this.http.post<BoardDetailDTO>('/api/boards', { name, description }))
  }
  async getBoard(id: number) {
    return toBoardData(await this.http.get<BoardDetailDTO>(`/api/boards/${id}`))
  }

  async createList(boardId: number, name: string) {
    const dto = await this.http.post<ListDTO>(`/api/boards/${boardId}/lists`, { name })
    return { id: dto.id, name: dto.name, isDone: dto.is_done, cards: [] }
  }
  async updateList(listId: number, changes: { name?: string; isDone?: boolean; archived?: boolean }) {
    await this.http.patch(`/api/lists/${listId}`, { name: changes.name, is_done: changes.isDone, archived: changes.archived })
  }

  async createCard(listId: number, title: string) {
    return toCardData(await this.http.post<CardDetailDTO>(`/api/lists/${listId}/cards`, { title }))
  }
  async getCard(cardId: number) {
    return toCardData(await this.http.get<CardDetailDTO>(`/api/cards/${cardId}`))
  }
  async updateCard(cardId: number, changes: CardChanges, version: number) {
    // Only send what's set: absent means "leave alone" on the server (and null means "clear").
    const body: Record<string, unknown> = { version }
    if (changes.title !== undefined) body.title = changes.title
    if (changes.description !== undefined) body.description = changes.description
    if (changes.dueAt !== undefined) body.due_at = changes.dueAt?.toISOString() ?? null
    if (changes.completed !== undefined) body.completed = changes.completed
    if (changes.archived !== undefined) body.archived = changes.archived
    return toCardData(await this.http.patch<CardDetailDTO>(`/api/cards/${cardId}`, body))
  }
  async moveCard(cardId: number, listId: number, afterId: number | null) {
    return toCardData(await this.http.post<CardDetailDTO>(`/api/cards/${cardId}/move`, { list_id: listId, after_id: afterId }))
  }
  async deleteCard(cardId: number) {
    await this.http.delete(`/api/cards/${cardId}`)
  }

  async setLabel(cardId: number, labelId: number, on: boolean) {
    const path = `/api/cards/${cardId}/labels/${labelId}`
    await (on ? this.http.put(path) : this.http.delete(path))
  }
  async setAssignee(cardId: number, userId: number, on: boolean) {
    const path = `/api/cards/${cardId}/assignees/${userId}`
    await (on ? this.http.put(path) : this.http.delete(path))
  }
  async addChecklistItem(cardId: number, text: string) {
    await this.http.post(`/api/cards/${cardId}/checklist`, { text })
  }
  async setChecklistItemDone(itemId: number, done: boolean) {
    await this.http.patch(`/api/checklist-items/${itemId}`, { done })
  }
  async deleteChecklistItem(itemId: number) {
    await this.http.delete(`/api/checklist-items/${itemId}`)
  }

  async listComments(cardId: number) {
    const { comments } = await this.http.get<{ comments: CommentDTO[] }>(`/api/cards/${cardId}/comments`)
    return comments.map(toComment)
  }
  async addComment(cardId: number, body: string) {
    await this.http.post(`/api/cards/${cardId}/comments`, { body })
  }
  async cardActivity(cardId: number) {
    return (await this.http.get<ActivityPageDTO>(`/api/cards/${cardId}/activity`, { limit: 50 })).activities.map(toActivity)
  }
  async boardActivity(boardId: number) {
    return (await this.http.get<ActivityPageDTO>(`/api/boards/${boardId}/activity`, { limit: 50 })).activities.map(toActivity)
  }

  async createLabel(boardId: number, name: string, color: LabelColor) {
    const dto = await this.http.post<LabelDTO>(`/api/boards/${boardId}/labels`, { name, color })
    return { id: dto.id, name: dto.name, color: dto.color }
  }
  async addMember(boardId: number, email: string, role: BoardRole) {
    await this.http.post(`/api/boards/${boardId}/members`, { email, role })
  }
  async setMemberRole(boardId: number, userId: number, role: BoardRole) {
    await this.http.patch(`/api/boards/${boardId}/members/${userId}`, { role })
  }
  async removeMember(boardId: number, userId: number) {
    await this.http.delete(`/api/boards/${boardId}/members/${userId}`)
  }

  async searchCards(search: CardSearch) {
    const { cards } = await this.http.get<CardSearchResponseDTO>('/api/cards', {
      assignee: search.assignee,
      completed: search.completed,
      overdue: search.overdue || undefined,
      q: search.q,
      limit: 200,
    })
    return cards.map(toSearchHit)
  }
}
