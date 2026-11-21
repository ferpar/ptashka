import { describe, expect, it } from 'vitest'
import { toCardData } from '../mappers'

describe('toCardData', () => {
  it('turns wire data into domain data', () => {
    const data = toCardData({
      id: 7, board_id: 1, list_id: 2, version: 3, title: 'T', description: null, position: 1024,
      due_at: '2026-12-01T09:00:00Z', completed_at: null, archived_at: null, created_by_id: 1,
      created_at: '2026-11-20T10:00:00Z', updated_at: '2026-11-20T10:00:00Z',
      label_ids: [4], assignee_ids: [5], checklist_done: 1, checklist_total: 2, comment_count: 0,
    })
    expect(data.dueAt).toEqual(new Date('2026-12-01T09:00:00Z'))
    expect(data.completedAt).toBeNull()
    expect(data).toMatchObject({ listId: 2, labelIds: [4], assigneeIds: [5], checklistTotal: 2 })
    expect(data.checklist).toBeUndefined() // Board-view cards carry counts only.
  })
})
