import { createResource, For } from 'solid-js'
import { useBoards } from '../../container/ContainerContext'
import type { Board } from '../../domain/board/Board'
import { dateTime, describeActivity, initials, relativeTime } from '../format'
import styles from './Board.module.css'

export function ActivityPanel(props: { board: Board; onClose: () => void }) {
  const repo = useBoards()
  const [entries, { refetch }] = createResource(() => repo.boardActivity(props.board.id))
  return (
    <aside class={styles.activityPanel} aria-label="Board activity">
      <div class={styles.activityHeader}>
        <h2>Activity</h2>
        <button class="ghost small" onClick={() => refetch()}>Refresh</button>
        <button class="ghost small" aria-label="Close" onClick={() => props.onClose()}>✕</button>
      </div>
      <div class={styles.activityList}>
        <For each={entries()} fallback={<p class="muted">Nothing yet.</p>}>
          {(entry) => (
            <div class={styles.activityItem}>
              <span class="avatar">{initials(entry.actor?.displayName ?? '?')}</span>
              <div>
                <strong>{entry.actor?.displayName ?? 'Someone'}</strong> {describeActivity(entry)}
                <div class="muted small" title={dateTime(entry.createdAt)}>{relativeTime(entry.createdAt)}</div>
              </div>
            </div>
          )}
        </For>
      </div>
    </aside>
  )
}
