import { ApiError } from '../../../api/http'
import type { BoardRepository } from '../BoardRepository'
import type { BoardData, CardChanges, CardData } from '../types'

export function cardData(overrides: Partial<CardData> & { id: number; listId: number }): CardData {
  return {
    boardId: 1,
    version: 1,
    title: `Card ${overrides.id}`,
    description: null,
    position: overrides.id * 1024,
    dueAt: null,
    completedAt: null,
    archivedAt: null,
    labelIds: [],
    assigneeIds: [],
    checklistDone: 0,
    checklistTotal: 0,
    commentCount: 0,
    ...overrides,
  }
}

/** An in-memory server with just enough behaviour for domain tests (moves into the done list
 * complete the card; stale versions get a 409). Methods a test doesn't need throw. */
export class FakeBoardRepository implements Partial<BoardRepository> {
  calls: string[] = []
  failNextMove = false
  cards = new Map<number, CardData>()

  constructor(private readonly board: BoardData) {
    for (const list of board.lists) for (const card of list.cards) this.cards.set(card.id, { ...card })
  }

  async getBoard(): Promise<BoardData> {
    return this.board
  }

  async getCard(cardId: number): Promise<CardData> {
    return { ...this.cards.get(cardId)! }
  }

  async moveCard(cardId: number, listId: number, afterId: number | null): Promise<CardData> {
    this.calls.push(`move ${cardId} → list ${listId} after ${afterId}`)
    if (this.failNextMove) {
      this.failNextMove = false
      throw new ApiError('list_id is not a list on this board', 422)
    }
    const target = this.board.lists.find((l) => l.id === listId)!
    const card = this.cards.get(cardId)!
    const updated = { ...card, listId, version: card.version + 1, completedAt: target.isDone ? new Date() : card.completedAt }
    this.cards.set(cardId, updated)
    return { ...updated }
  }

  async updateCard(cardId: number, changes: CardChanges, version: number): Promise<CardData> {
    this.calls.push(`update ${cardId} v${version}`)
    const card = this.cards.get(cardId)!
    if (version !== card.version) throw new ApiError('Card was modified', 409, { current_version: card.version })
    const updated = { ...card, title: changes.title ?? card.title, version: card.version + 1 }
    this.cards.set(cardId, updated)
    return { ...updated }
  }

  asRepository(): BoardRepository {
    return this as unknown as BoardRepository
  }
}

export function sampleBoard(): BoardData {
  return {
    id: 1,
    name: 'Home',
    description: null,
    myRole: 'owner',
    members: [],
    labels: [],
    lists: [
      { id: 10, name: 'To do', isDone: false, cards: [cardData({ id: 1, listId: 10 }), cardData({ id: 2, listId: 10 })] },
      { id: 20, name: 'Done', isDone: true, cards: [cardData({ id: 3, listId: 20 })] },
    ],
  }
}
