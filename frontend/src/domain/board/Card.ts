import { createStore, reconcile, type SetStoreFunction } from 'solid-js/store'
import type { CardData, ChecklistItem } from './types'

type CardState = Omit<CardData, 'checklist'> & { checklist: ChecklistItem[] | null }

/**
 * A card: a reactive domain object. Its state lives in a Solid store *inside* the class (stores only
 * track plain objects and arrays, not class instances), and the class exposes ordinary getters.
 *
 * A component that reads `card.title` subscribes to exactly that value: when the title changes,
 * only the DOM text showing it updates. No store layer, no `.get()`, no re-render.
 */
export class Card {
  readonly id: number
  private readonly state: CardState
  private readonly setState: SetStoreFunction<CardState>

  constructor(data: CardData) {
    this.id = data.id
    ;[this.state, this.setState] = createStore<CardState>({ ...data, checklist: data.checklist ?? null })
  }

  get listId() { return this.state.listId }
  get version() { return this.state.version }
  get title() { return this.state.title }
  get description() { return this.state.description }
  get dueAt() { return this.state.dueAt }
  get completedAt() { return this.state.completedAt }
  get labelIds() { return this.state.labelIds }
  get assigneeIds() { return this.state.assigneeIds }
  get checklistDone() { return this.state.checklistDone }
  get checklistTotal() { return this.state.checklistTotal }
  get commentCount() { return this.state.commentCount }
  /** null until the card has been loaded on its own (the board view only carries counts). */
  get checklist() { return this.state.checklist }

  // Derived values are getters too: recomputed on read, and still tracked.
  get isCompleted() { return this.state.completedAt !== null }
  get isArchived() { return this.state.archivedAt !== null }
  get isOverdue() {
    return this.state.dueAt !== null && !this.isCompleted && this.state.dueAt.getTime() < Date.now()
  }

  /** The server's version of this card wins: merge it in (only changed values notify readers). */
  applyServer(data: CardData): void {
    this.setState(reconcile({ ...data, checklist: data.checklist ?? this.state.checklist }, { merge: true }))
  }

  /** Optimistic placement, before the server confirms it. */
  placeIn(listId: number): void {
    this.setState('listId', listId)
  }
}
