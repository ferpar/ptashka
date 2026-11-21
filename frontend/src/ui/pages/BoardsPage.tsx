import { A, useNavigate } from '@solidjs/router'
import { createResource, For, Show } from 'solid-js'
import { useBoards } from '../../container/ContainerContext'
import { createErrorReporter } from '../common/errors'
import styles from './Pages.module.css'

export function BoardsPage() {
  const repo = useBoards()
  const navigate = useNavigate()
  const { report, Banner } = createErrorReporter()
  // createResource: loading and error state for an async value, no store needed.
  const [boards] = createResource(() => repo.listBoards())

  const create = async (e: SubmitEvent) => {
    e.preventDefault()
    const input = (e.currentTarget as HTMLFormElement).elements.namedItem('name') as HTMLInputElement
    const board = await report(repo.createBoard(input.value.trim(), null))
    if (board) navigate(`/boards/${board.id}`)
  }

  return (
    <div class={styles.page}>
      <h1>Your boards</h1>
      <Show when={!boards.loading} fallback={<p class="muted">Loading…</p>}>
        <div class={styles.boardGrid}>
          <For each={boards()}>
            {(board) => (
              <A href={`/boards/${board.id}`} class={styles.boardTile}>
                <strong>{board.name}</strong>
                <Show when={board.description}><span class="muted small">{board.description}</span></Show>
                <span class={`small ${styles.role}`}>{board.myRole}</span>
              </A>
            )}
          </For>
          <form class={styles.boardTile} onSubmit={create}>
            <strong>New board</strong>
            <input name="name" placeholder="Board name" required maxLength={100} />
            <button class="primary">Create</button>
          </form>
        </div>
      </Show>
      <Banner />
    </div>
  )
}
