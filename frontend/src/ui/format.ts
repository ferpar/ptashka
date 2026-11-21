/** Presentation helpers: framework-free, easy to test. */
import type { ActivityEntry, LabelColor } from '../domain/board/types'

export const labelColor = (color: LabelColor) => `var(--label-${color})`

export function initials(name: string): string {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]!.toUpperCase()).join('') || '?'
}

const dateFormat = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short' })
const dateTimeFormat = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })

export const shortDate = (d: Date) => dateFormat.format(d)
export const dateTime = (d: Date) => dateTimeFormat.format(d)

/** `<input type="datetime-local">` speaks local wall-clock time without a zone; the API wants an instant. */
export function toLocalInput(d: Date | null): string {
  if (!d) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}
export const fromLocalInput = (value: string): Date | null => (value ? new Date(value) : null)

export function relativeTime(d: Date, now = Date.now()): string {
  const seconds = Math.round((now - d.getTime()) / 1000)
  if (seconds < 60) return 'just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`
  return shortDate(d)
}

const q = (s: unknown) => `“${String(s ?? '')}”`

/** One activity entry as a sentence (without the actor, which the UI shows separately). */
export function describeActivity(entry: ActivityEntry): string {
  const d = entry.data
  const card = q(d.card_title)
  switch (entry.kind) {
    case 'board.created': return `created this board`
    case 'board.updated': return `updated the board (${(d.changed as string[]).join(', ')})`
    case 'board.archived': return 'archived the board'
    case 'board.restored': return 'restored the board'
    case 'member.added': return `added ${d.user_name} as ${d.role}`
    case 'member.role_changed': return `made ${d.user_name} ${d.to_role} (was ${d.from_role})`
    case 'member.removed': return d.left ? 'left the board' : `removed ${d.user_name}`
    case 'list.created': return `added list ${q(d.list_name)}`
    case 'list.updated': return `renamed list ${q((d.from as Record<string, unknown>)?.name)} to ${q((d.to as Record<string, unknown>)?.name)}`
    case 'list.moved': return `moved list ${q(d.list_name)}`
    case 'list.archived': return `archived list ${q(d.list_name)}`
    case 'list.restored': return `restored list ${q(d.list_name)}`
    case 'list.set_done': return d.is_done ? `made ${q(d.list_name)} the done list` : `unset ${q(d.list_name)} as done list`
    case 'card.created': return `added ${card} to ${d.list_name}`
    case 'card.updated': return `edited ${card} (${(d.changed as string[]).join(', ')})`
    case 'card.moved': return `moved ${card} from ${d.from_list} to ${d.to_list}`
    case 'card.completed': return `completed ${card}`
    case 'card.reopened': return `reopened ${card}`
    case 'card.archived': return `archived ${card}`
    case 'card.restored': return `restored ${card}`
    case 'card.deleted': return `deleted ${card}`
    case 'label.added': return `labelled ${card} ${q(d.label_name)}`
    case 'label.removed': return `removed label ${q(d.label_name)} from ${card}`
    case 'assignee.added': return `assigned ${d.user_name} to ${card}`
    case 'assignee.removed': return `unassigned ${d.user_name} from ${card}`
    case 'checklist.added': return `added ${q(d.text)} to the checklist of ${card}`
    case 'checklist.checked': return `checked ${q(d.text)} on ${card}`
    case 'checklist.unchecked': return `unchecked ${q(d.text)} on ${card}`
    case 'comment.added': return `commented on ${card}: ${q(d.excerpt)}`
  }
}
