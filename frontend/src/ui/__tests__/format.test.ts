import { describe, expect, it } from 'vitest'
import type { ActivityEntry } from '../../domain/board/types'
import { describeActivity, fromLocalInput, initials, toLocalInput } from '../format'

const entry = (kind: ActivityEntry['kind'], data: Record<string, unknown>): ActivityEntry => ({
  id: 1, boardId: 1, cardId: 1, actor: null, kind, data, createdAt: new Date(),
})

describe('format', () => {
  it('describes activity entries as sentences', () => {
    expect(describeActivity(entry('card.moved', { card_title: 'Ship', from_list: 'To do', to_list: 'Done' })))
      .toBe('moved “Ship” from To do to Done')
    expect(describeActivity(entry('member.removed', { user_name: 'Bob', left: true }))).toBe('left the board')
  })

  it('round-trips datetime-local values through real instants', () => {
    const d = new Date(2026, 11, 1, 9, 30)
    expect(fromLocalInput(toLocalInput(d))).toEqual(d)
    expect(fromLocalInput('')).toBeNull()
  })

  it('makes initials', () => {
    expect(initials('Olena Kovalenko')).toBe('OK')
    expect(initials('')).toBe('?')
  })
})
