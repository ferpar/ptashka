import { createSignal } from 'solid-js'
import type { Card } from './Card'

/** A column. Its cards are an ordered array of Card objects (the same objects the Board owns). */
export class BoardList {
  readonly id: number
  private readonly name$ = createSignal('')
  private readonly isDone$ = createSignal(false)
  private readonly cards$ = createSignal<Card[]>([])

  constructor(id: number, name: string, isDone: boolean, cards: Card[]) {
    this.id = id
    this.name$[1](name)
    this.isDone$[1](isDone)
    this.cards$[1](cards)
  }

  get name() { return this.name$[0]() }
  get isDone() { return this.isDone$[0]() }
  get cards() { return this.cards$[0]() }
  /** What the board shows: archived cards stay in the array (they keep their slot) but are hidden. */
  get visibleCards() { return this.cards.filter((c) => !c.isArchived) }

  rename(name: string) { this.name$[1](name) }
  setDone(isDone: boolean) { this.isDone$[1](isDone) }

  remove(card: Card): void {
    this.cards$[1]((cards) => cards.filter((c) => c !== card))
  }

  /** Insert right after `after` (null: at the top). */
  insertAfter(card: Card, after: Card | null): void {
    this.cards$[1]((cards) => {
      const without = cards.filter((c) => c !== card)
      const index = after ? without.indexOf(after) + 1 : 0
      return [...without.slice(0, index), card, ...without.slice(index)]
    })
  }

  append(card: Card): void {
    this.cards$[1]((cards) => [...cards, card])
  }
}
