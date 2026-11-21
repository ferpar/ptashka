import { A } from '@solidjs/router'
import { createResource, createSignal, For, Show } from 'solid-js'
import { useBoards } from '../../container/ContainerContext'
import type { CardSearchHit } from '../../domain/board/types'
import { shortDate } from '../format'
import styles from './Pages.module.css'

/** Open cards assigned to you, on every board: the same search agents will use. */
export function MyTasksPage() {
  const repo = useBoards()
  const [overdueOnly, setOverdueOnly] = createSignal(false)
  const [text, setText] = createSignal('')
  const [hits] = createResource(
    () => ({ overdue: overdueOnly(), q: text() }),
    ({ overdue, q }) => repo.searchCards({ assignee: 'me', completed: false, overdue, q: q || undefined }),
  )

  const byBoard = () => {
    const groups = new Map<string, CardSearchHit[]>()
    for (const hit of hits() ?? []) groups.set(hit.boardName, [...(groups.get(hit.boardName) ?? []), hit])
    return [...groups.entries()]
  }

  return (
    <div class={styles.page}>
      <h1>My tasks</h1>
      <div class="row">
        <input type="search" placeholder="Search…" onInput={(e) => setText(e.currentTarget.value)} />
        <label class="row small"><input type="checkbox" onChange={(e) => setOverdueOnly(e.currentTarget.checked)} /> Overdue only</label>
      </div>
      <Show when={hits()} fallback={<p class="muted">Loading…</p>}>
        <Show when={byBoard().length} fallback={<p class="muted">Nothing assigned to you. Enjoy it.</p>}>
          <For each={byBoard()}>
            {([boardName, cards]) => (
              <section class={styles.taskGroup}>
                <h2>{boardName}</h2>
                <For each={cards}>
                  {(hit) => (
                    <A href={`/boards/${hit.boardId}?card=${hit.id}`} class={styles.taskRow}>
                      <span>{hit.title}</span>
                      <span class="muted small">{hit.listName}</span>
                      <Show when={hit.dueAt}>
                        {(due) => (
                          <span class="small" classList={{ error: due().getTime() < Date.now() }}>due {shortDate(due())}</span>
                        )}
                      </Show>
                    </A>
                  )}
                </For>
              </section>
            )}
          </For>
        </Show>
      </Show>
    </div>
  )
}
