import type { Edge } from '@atlaskit/pragmatic-drag-and-drop-hitbox/types'
import { createSignal, For, onCleanup, onMount, Show } from 'solid-js'
import type { Board } from '../../domain/board/Board'
import type { Card } from '../../domain/board/Card'
import { initials, labelColor, shortDate } from '../format'
import styles from './Board.module.css'
import { cardDnd } from './dnd'

/**
 * A card on the board. Note what's absent: no store, no subscription code. It reads the Card
 * domain object directly (`props.card.title`), and Solid updates exactly the bits that change.
 * (Props aren't destructured: `props.card` must be read inside JSX to stay reactive.)
 */
export function CardTile(props: { board: Board; card: Card; onOpen: () => void }) {
  let element!: HTMLDivElement
  const [edge, setEdge] = createSignal<Edge | null>(null)

  onMount(() => {
    if (props.board.canContribute) onCleanup(cardDnd(element, props.card, setEdge))
  })

  return (
    <div
      ref={element}
      class={styles.card}
      classList={{ [styles.completed!]: props.card.isCompleted, [styles.edgeTop!]: edge() === 'top', [styles.edgeBottom!]: edge() === 'bottom' }}
      data-testid={`card-${props.card.id}`}
      role="button"
      tabIndex={0}
      onClick={() => props.onOpen()}
      onKeyDown={(e) => e.key === 'Enter' && props.onOpen()}
    >
      <Show when={props.card.labelIds.length}>
        <div class={styles.cardLabels}>
          <For each={props.card.labelIds}>
            {(id) => (
              <Show when={props.board.label(id)}>
                {(label) => <span class="label-chip" style={{ background: labelColor(label().color) }}>{label().name}</span>}
              </Show>
            )}
          </For>
        </div>
      </Show>

      <span class={styles.cardTitle}>{props.card.title}</span>

      <div class={styles.badges}>
        <Show when={props.card.dueAt}>
          {(due) => (
            <span class={styles.badge} classList={{ [styles.overdue!]: props.card.isOverdue, [styles.done!]: props.card.isCompleted }}>
              ◷ {shortDate(due())}
            </span>
          )}
        </Show>
        <Show when={props.card.checklistTotal > 0}>
          <span class={styles.badge} classList={{ [styles.done!]: props.card.checklistDone === props.card.checklistTotal }}>
            ☑ {props.card.checklistDone}/{props.card.checklistTotal}
          </span>
        </Show>
        <Show when={props.card.commentCount > 0}>
          <span class={styles.badge}>💬 {props.card.commentCount}</span>
        </Show>
        <span class={styles.assignees}>
          <For each={props.card.assigneeIds}>
            {(id) => {
              const name = () => props.board.member(id)?.displayName ?? '?'
              return <span class="avatar" title={name()}>{initials(name())}</span>
            }}
          </For>
        </span>
      </div>
    </div>
  )
}
