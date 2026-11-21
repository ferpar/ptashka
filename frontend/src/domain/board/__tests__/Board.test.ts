import { createComputed, createRoot } from 'solid-js'
import { describe, expect, it } from 'vitest'
import { Board, ConflictError } from '../Board'
import { FakeBoardRepository, sampleBoard } from './FakeBoardRepository'

async function setup() {
  const fake = new FakeBoardRepository(sampleBoard())
  const board = await Board.load(fake.asRepository(), 1)
  const [todo, done] = board.lists
  return { fake, board, todo, done, card: (id: number) => board.card(id)! }
}

const titles = (list: { cards: { title: string }[] }) => list.cards.map((c) => c.title)

describe('fine-grained reactivity (no UI involved)', () => {
  it('a reader of one card is notified only when that card changes', async () => {
    const { card } = await setup()
    let reads = 0
    const dispose = createRoot((dispose) => {
      createComputed(() => {
        void card(1).title // Subscribe to card 1's title, like `{card.title}` in JSX would.
        reads++
      })
      return dispose
    })
    expect(reads).toBe(1)

    card(2).applyServer({ ...(await new FakeBoardRepository(sampleBoard()).getCard(2)), title: 'Other card renamed' })
    expect(reads).toBe(1) // Another card changed: nothing to do.

    card(1).applyServer({ ...(await new FakeBoardRepository(sampleBoard()).getCard(1)), title: 'Renamed' })
    expect(reads).toBe(2) // This card's title changed: exactly one update.
    dispose()
  })
})

describe('moving cards', () => {
  it('moves optimistically, then applies the server\'s answer', async () => {
    const { board, todo, done, card } = await setup()
    const move = board.moveCard(card(1), done, card(3))

    // Before the server answers, the card is already where it was dropped.
    expect(titles(done)).toEqual(['Card 3', 'Card 1'])
    expect(titles(todo)).toEqual(['Card 2'])
    expect(card(1).isCompleted).toBe(false) // The client doesn't guess business rules...

    await move
    expect(card(1).isCompleted).toBe(true) // ...the server's answer says it's completed now.
    expect(card(1).version).toBe(2)
  })

  it('puts the card back if the server refuses', async () => {
    const { fake, board, todo, done, card } = await setup()
    fake.failNextMove = true

    await expect(board.moveCard(card(2), done, null)).rejects.toThrow('not a list on this board')
    expect(titles(todo)).toEqual(['Card 1', 'Card 2'])
    expect(titles(done)).toEqual(['Card 3'])
    expect(card(2).listId).toBe(todo.id)
  })

  it('does not call the server when dropped where it already was', async () => {
    const { fake, board, todo, card } = await setup()
    await board.moveCard(card(2), todo, card(1))
    expect(fake.calls).toEqual([])
  })
})

describe('editing cards', () => {
  it('sends the version it has', async () => {
    const { fake, board, card } = await setup()
    await board.updateCard(card(1), { title: 'New title' })
    expect(fake.calls).toEqual(['update 1 v1'])
    expect(card(1).title).toBe('New title')
  })

  it('on a conflict, reloads the card and says so', async () => {
    const { fake, board, card } = await setup()
    // Someone else edits card 1 on the server (version 1 → 2).
    fake.cards.set(1, { ...fake.cards.get(1)!, title: 'Their title', version: 2 })

    await expect(board.updateCard(card(1), { title: 'My title' })).rejects.toBeInstanceOf(ConflictError)
    expect(card(1).title).toBe('Their title') // Their change is shown, not overwritten.
    expect(card(1).version).toBe(2) // A retry will now be based on the latest version.
  })
})
