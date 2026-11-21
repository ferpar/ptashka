import { useParams, useSearchParams } from '@solidjs/router'
import { createEffect, createResource, createSignal, For, onCleanup, Show } from 'solid-js'
import { useBoards } from '../../container/ContainerContext'
import { Board } from '../../domain/board/Board'
import { createErrorReporter } from '../common/errors'
import { initials } from '../format'
import { ActivityPanel } from './ActivityPanel'
import styles from './Board.module.css'
import { BoardSettings } from './BoardSettings'
import { CardModal } from './CardModal'
import { monitorCardDrops } from './dnd'
import { ListColumn } from './ListColumn'

export function BoardPage() {
  const params = useParams<{ id: string }>()
  const [search, setSearch] = useSearchParams<{ card?: string }>()
  const repo = useBoards()
  const errors = createErrorReporter()
  const [board] = createResource(() => Number(params.id), (id) => Board.load(repo, id))
  const [showActivity, setShowActivity] = createSignal(false)
  const [showSettings, setShowSettings] = createSignal(false)

  // The open card lives in the URL (?card=12), so it can be linked to (My tasks does).
  const openCard = () => {
    const id = Number(search.card)
    return id ? board()?.card(id) : undefined
  }

  // One monitor for every drop on this board; re-attached if the board is reloaded.
  createEffect(() => {
    const b = board()
    if (!b?.canContribute) return
    onCleanup(monitorCardDrops(b, (card, to, after) => void errors.report(b.moveCard(card, to, after))))
  })

  return (
    <Show when={board()} fallback={<p class="muted" style={{ padding: '24px' }}>{board.error ? String(board.error.message) : 'Loading…'}</p>}>
      {(b) => (
        <div class={styles.boardPage}>
          <div class={styles.boardHeader}>
            <h1>{b().name}</h1>
            <div class={styles.members}>
              <For each={b().members}>
                {(m) => <span class="avatar" title={`${m.displayName} (${m.role})`}>{initials(m.displayName)}</span>}
              </For>
            </div>
            <span class="muted small">You are {b().myRole === 'owner' ? 'an' : 'a'} {b().myRole}</span>
            <div class={styles.headerActions}>
              <button onClick={() => setShowActivity((v) => !v)}>Activity</button>
              <Show when={b().canEdit}>
                <button onClick={() => setShowSettings(true)}>Members & labels</button>
              </Show>
            </div>
          </div>

          <div class={styles.columns}>
            <For each={b().lists}>
              {(list) => <ListColumn board={b()} list={list} report={errors.report} onOpenCard={(card) => setSearch({ card: String(card.id) })} />}
            </For>
            <Show when={b().canEdit}>
              <AddList board={b()} report={errors.report} />
            </Show>
          </div>

          <Show when={showActivity()}>
            <ActivityPanel board={b()} onClose={() => setShowActivity(false)} />
          </Show>
          <Show when={openCard()}>
            {(card) => <CardModal board={b()} card={card()} onClose={() => setSearch({ card: undefined })} />}
          </Show>
          <Show when={showSettings()}>
            <BoardSettings board={b()} onClose={() => setShowSettings(false)} />
          </Show>
          <errors.Banner />
        </div>
      )}
    </Show>
  )
}

function AddList(props: { board: Board; report: ReturnType<typeof createErrorReporter>['report'] }) {
  const [open, setOpen] = createSignal(false)
  const submit = async (e: SubmitEvent) => {
    e.preventDefault()
    const input = (e.currentTarget as HTMLFormElement).elements.namedItem('name') as HTMLInputElement
    await props.report(props.board.addList(input.value.trim()))
    input.value = ''
  }
  return (
    <div class={styles.addList}>
      <Show when={open()} fallback={<button class="ghost" onClick={() => setOpen(true)}>+ Add a list</button>}>
        <form class="stack" onSubmit={submit}>
          <input name="name" placeholder="List name" required maxLength={100} autofocus />
          <div class="row">
            <button class="primary">Add list</button>
            <button type="button" class="ghost" onClick={() => setOpen(false)}>Cancel</button>
          </div>
        </form>
      </Show>
    </div>
  )
}
