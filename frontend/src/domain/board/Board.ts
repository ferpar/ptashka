import { createSignal } from 'solid-js'
import type { BoardRole, LabelColor } from '../../api/dtos'
import { ApiError } from '../../api/http'
import { BoardList } from './BoardList'
import type { BoardRepository } from './BoardRepository'
import { Card } from './Card'
import type { BoardData, CardChanges, Label, Member } from './types'

/** The card changed on the server since it was loaded; it has been reloaded with the latest version. */
export class ConflictError extends Error {
  constructor() {
    super('Someone else changed this card in the meantime. It has been reloaded: please check and try again.')
    this.name = 'ConflictError'
  }
}

const RANK: Record<BoardRole, number> = { viewer: 0, contributor: 1, editor: 2, owner: 3 }

/**
 * The board aggregate: it owns its lists and cards, and every change to them goes through its
 * methods. This is where the frontend has real behaviour (a rich domain model): optimistic moves
 * with rollback, conflict handling, reconciling with the server.
 *
 * The rule throughout: the client *predicts* (instant feedback), the server *decides* (its answer
 * is applied on top). Business rules like "moving into Done completes the card" are never
 * reimplemented here; they arrive in the server's response.
 */
export class Board {
  readonly id: number
  readonly myRole: BoardRole
  private readonly name$ = createSignal('')
  private readonly lists$ = createSignal<BoardList[]>([])
  private readonly members$ = createSignal<Member[]>([])
  private readonly labels$ = createSignal<Label[]>([])
  private readonly cards = new Map<number, Card>()

  private constructor(
    data: BoardData,
    private readonly repo: BoardRepository,
  ) {
    this.id = data.id
    this.myRole = data.myRole
    this.apply(data)
  }

  static async load(repo: BoardRepository, id: number): Promise<Board> {
    return new Board(await repo.getBoard(id), repo)
  }

  /** (Re)build from server data, reusing existing Card objects so open views keep working. */
  private apply(data: BoardData): void {
    this.name$[1](data.name)
    this.members$[1](data.members)
    this.labels$[1](data.labels)
    this.lists$[1](
      data.lists.map((l) => new BoardList(l.id, l.name, l.isDone, l.cards.map((c) => this.upsertCard(c)))),
    )
  }

  private upsertCard(data: BoardData['lists'][number]['cards'][number]): Card {
    const existing = this.cards.get(data.id)
    if (existing) {
      existing.applyServer(data)
      return existing
    }
    const card = new Card(data)
    this.cards.set(card.id, card)
    return card
  }

  async reload(): Promise<void> {
    this.apply(await this.repo.getBoard(this.id))
  }

  get name() { return this.name$[0]() }
  get lists() { return this.lists$[0]() }
  get members() { return this.members$[0]() }
  get labels() { return this.labels$[0]() }

  // What the current user may do (the server enforces it; this only shapes the UI).
  get canContribute() { return RANK[this.myRole] >= RANK.contributor }
  get canEdit() { return RANK[this.myRole] >= RANK.editor }
  get isOwner() { return this.myRole === 'owner' }

  card(id: number): Card | undefined {
    return this.cards.get(id)
  }

  listOf(card: Card): BoardList | undefined {
    return this.lists.find((l) => l.id === card.listId)
  }

  member(userId: number): Member | undefined {
    return this.members.find((m) => m.userId === userId)
  }

  label(id: number): Label | undefined {
    return this.labels.find((l) => l.id === id)
  }

  // ── Cards ──

  async addCard(list: BoardList, title: string): Promise<Card> {
    const card = this.upsertCard(await this.repo.createCard(list.id, title))
    list.append(card)
    return card
  }

  /**
   * Move `card` into `to`, right after `after` (null: top). The UI updates immediately; if the
   * server refuses, the card goes back where it was and the error is re-thrown for the UI to show.
   */
  async moveCard(card: Card, to: BoardList, after: Card | null): Promise<void> {
    const from = this.listOf(card)
    if (!from) return
    const before = from.cards.indexOf(card)
    const previous = before > 0 ? from.cards[before - 1] : null
    if (from === to && previous === after) return // Dropped where it already was.

    from.remove(card)
    to.insertAfter(card, after)
    card.placeIn(to.id)
    try {
      card.applyServer(await this.repo.moveCard(card.id, to.id, after?.id ?? null))
    } catch (err) {
      to.remove(card)
      from.insertAfter(card, previous)
      card.placeIn(from.id)
      throw err
    }
  }

  /** Edit fields. Sends the version we have; on 409 the card is reloaded and ConflictError thrown. */
  async updateCard(card: Card, changes: CardChanges): Promise<void> {
    try {
      card.applyServer(await this.repo.updateCard(card.id, changes, card.version))
    } catch (err) {
      if (err instanceof ApiError && err.isConflict) {
        await this.refreshCard(card)
        throw new ConflictError()
      }
      throw err
    }
  }

  async deleteCard(card: Card): Promise<void> {
    await this.repo.deleteCard(card.id)
    this.listOf(card)?.remove(card)
    this.cards.delete(card.id)
  }

  /** Reload one card from the server (with its checklist). */
  async refreshCard(card: Card): Promise<void> {
    card.applyServer(await this.repo.getCard(card.id))
  }

  async toggleLabel(card: Card, labelId: number): Promise<void> {
    await this.repo.setLabel(card.id, labelId, !card.labelIds.includes(labelId))
    await this.refreshCard(card)
  }

  async toggleAssignee(card: Card, userId: number): Promise<void> {
    await this.repo.setAssignee(card.id, userId, !card.assigneeIds.includes(userId))
    await this.refreshCard(card)
  }

  async addChecklistItem(card: Card, text: string): Promise<void> {
    await this.repo.addChecklistItem(card.id, text)
    await this.refreshCard(card)
  }

  async setChecklistItemDone(card: Card, itemId: number, done: boolean): Promise<void> {
    await this.repo.setChecklistItemDone(itemId, done)
    await this.refreshCard(card)
  }

  async deleteChecklistItem(card: Card, itemId: number): Promise<void> {
    await this.repo.deleteChecklistItem(itemId)
    await this.refreshCard(card)
  }

  async addComment(card: Card, body: string): Promise<void> {
    await this.repo.addComment(card.id, body)
    await this.refreshCard(card) // Updates the comment count on the board.
  }

  // ── Lists, labels, members ──

  async addList(name: string): Promise<void> {
    const data = await this.repo.createList(this.id, name)
    this.lists$[1]((lists) => [...lists, new BoardList(data.id, data.name, data.isDone, [])])
  }

  async renameList(list: BoardList, name: string): Promise<void> {
    const previous = list.name
    list.rename(name)
    try {
      await this.repo.updateList(list.id, { name })
    } catch (err) {
      list.rename(previous)
      throw err
    }
  }

  async makeDoneList(list: BoardList): Promise<void> {
    await this.repo.updateList(list.id, { isDone: true })
    for (const l of this.lists) l.setDone(l === list)
  }

  async createLabel(name: string, color: LabelColor): Promise<void> {
    const label = await this.repo.createLabel(this.id, name, color)
    this.labels$[1]((labels) => [...labels, label].sort((a, b) => a.name.localeCompare(b.name)))
  }

  async addMember(email: string, role: BoardRole): Promise<void> {
    await this.repo.addMember(this.id, email, role)
    await this.reload()
  }

  async setMemberRole(userId: number, role: BoardRole): Promise<void> {
    await this.repo.setMemberRole(this.id, userId, role)
    await this.reload()
  }

  async removeMember(userId: number): Promise<void> {
    await this.repo.removeMember(this.id, userId)
    await this.reload()
  }
}
