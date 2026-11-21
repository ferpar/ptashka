import { createSignal, For, onCleanup, onMount, Show } from 'solid-js'
import type { Board } from '../../domain/board/Board'
import type { BoardList } from '../../domain/board/BoardList'
import type { Card } from '../../domain/board/Card'
import type { Report } from '../common/errors'
import styles from './Board.module.css'
import { CardTile } from './CardTile'
import { listDropTarget } from './dnd'

export function ListColumn(props: { board: Board; list: BoardList; report: Report; onOpenCard: (card: Card) => void }) {
  let body!: HTMLDivElement
  const [over, setOver] = createSignal(false)
  const [renaming, setRenaming] = createSignal(false)
  const [adding, setAdding] = createSignal(false)

  onMount(() => {
    if (props.board.canContribute) onCleanup(listDropTarget(body, props.list, setOver))
  })

  const rename = async (name: string) => {
    setRenaming(false)
    if (name.trim() && name.trim() !== props.list.name) await props.report(props.board.renameList(props.list, name.trim()))
  }

  const addCard = async (e: SubmitEvent) => {
    e.preventDefault()
    const input = (e.currentTarget as HTMLFormElement).elements.namedItem('title') as HTMLInputElement
    if (!input.value.trim()) return
    await props.report(props.board.addCard(props.list, input.value.trim()))
    input.value = ''
    input.focus()
  }

  return (
    <section class={styles.column} aria-label={props.list.name}>
      <header class={styles.columnHeader}>
        <Show
          when={renaming()}
          fallback={
            <h2 onDblClick={() => props.board.canEdit && setRenaming(true)} title={props.board.canEdit ? 'Double-click to rename' : undefined}>
              {props.list.name}
            </h2>
          }
        >
          <input
            value={props.list.name}
            autofocus
            maxLength={100}
            onBlur={(e) => rename(e.currentTarget.value)}
            onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.blur()}
          />
        </Show>
        <span class="muted small">{props.list.visibleCards.length}</span>
        <Show
          when={props.list.isDone}
          fallback={
            <Show when={props.board.canEdit}>
              <button class="ghost small" title="Cards moved here get completed" onClick={() => props.report(props.board.makeDoneList(props.list))}>
                Set as done
              </button>
            </Show>
          }
        >
          <span class={styles.doneBadge} title="Moving a card here completes it">✓ done list</span>
        </Show>
      </header>

      <div ref={body} class={styles.cards} classList={{ [styles.dropOver!]: over() }}>
        <For each={props.list.visibleCards}>
          {(card) => <CardTile board={props.board} card={card} onOpen={() => props.onOpenCard(card)} />}
        </For>
      </div>

      <Show when={props.board.canEdit}>
        <Show when={adding()} fallback={<button class={`ghost ${styles.addCard}`} onClick={() => setAdding(true)}>+ Add a card</button>}>
          <form class={`stack ${styles.composer}`} onSubmit={addCard}>
            <textarea
              name="title"
              rows="2"
              placeholder="What needs doing?"
              maxLength={200}
              autofocus
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  e.currentTarget.form?.requestSubmit()
                }
              }}
            />
            <div class="row">
              <button class="primary">Add card</button>
              <button type="button" class="ghost" onClick={() => setAdding(false)}>Cancel</button>
            </div>
          </form>
        </Show>
      </Show>
    </section>
  )
}
