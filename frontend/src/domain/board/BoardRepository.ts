/** Everything the board domain needs from the server. The domain depends on this interface;
 * tests pass a fake, the app passes HttpBoardRepository. */
import type { BoardRole, LabelColor } from '../../api/dtos'
import type {
  ActivityEntry,
  BoardData,
  BoardSummary,
  CardChanges,
  CardData,
  CardSearchHit,
  Comment,
  Label,
  ListData,
} from './types'

export interface CardSearch {
  assignee?: 'me' | number
  completed?: boolean
  overdue?: boolean
  q?: string
}

export interface BoardRepository {
  listBoards(): Promise<BoardSummary[]>
  createBoard(name: string, description: string | null): Promise<BoardData>
  getBoard(id: number): Promise<BoardData>

  createList(boardId: number, name: string): Promise<ListData>
  updateList(listId: number, changes: { name?: string; isDone?: boolean; archived?: boolean }): Promise<void>

  createCard(listId: number, title: string): Promise<CardData>
  getCard(cardId: number): Promise<CardData>
  /** `version`: the version these changes are based on (the server answers 409 if it moved on). */
  updateCard(cardId: number, changes: CardChanges, version: number): Promise<CardData>
  moveCard(cardId: number, listId: number, afterId: number | null): Promise<CardData>
  deleteCard(cardId: number): Promise<void>

  setLabel(cardId: number, labelId: number, on: boolean): Promise<void>
  setAssignee(cardId: number, userId: number, on: boolean): Promise<void>
  addChecklistItem(cardId: number, text: string): Promise<void>
  setChecklistItemDone(itemId: number, done: boolean): Promise<void>
  deleteChecklistItem(itemId: number): Promise<void>

  listComments(cardId: number): Promise<Comment[]>
  addComment(cardId: number, body: string): Promise<void>
  cardActivity(cardId: number): Promise<ActivityEntry[]>
  boardActivity(boardId: number): Promise<ActivityEntry[]>

  createLabel(boardId: number, name: string, color: LabelColor): Promise<Label>
  addMember(boardId: number, email: string, role: BoardRole): Promise<void>
  setMemberRole(boardId: number, userId: number, role: BoardRole): Promise<void>
  removeMember(boardId: number, userId: number): Promise<void>

  searchCards(search: CardSearch): Promise<CardSearchHit[]>
}
