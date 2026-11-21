import { render, screen } from '@solidjs/testing-library'
import { describe, expect, it } from 'vitest'
import { Board } from '../../domain/board/Board'
import { FakeBoardRepository, cardData, sampleBoard } from '../../domain/board/__tests__/FakeBoardRepository'
import { CardTile } from '../board/CardTile'

describe('CardTile', () => {
  it('updates in place when the domain object changes: same DOM node, new text', async () => {
    const board = await Board.load(new FakeBoardRepository(sampleBoard()).asRepository(), 1)
    const card = board.card(1)!
    render(() => <CardTile board={board} card={card} onOpen={() => {}} />)

    const tile = screen.getByTestId('card-1')
    expect(tile).toHaveTextContent('Card 1')

    // A change arrives (e.g. the server's answer to an edit). No store, no re-render call:
    card.applyServer(cardData({ id: 1, listId: 10, title: 'Renamed', completedAt: new Date(), checklistDone: 1, checklistTotal: 2 }))

    expect(screen.getByTestId('card-1')).toBe(tile) // The very same element...
    expect(tile).toHaveTextContent('Renamed') // ...with its text updated,
    expect(tile).toHaveTextContent('☑ 1/2') // a badge that appeared,
    expect(tile.className).toMatch(/completed/) // and the completed styling.
  })
})
