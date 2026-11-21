import { createResource, createSignal, For, onMount, Show } from 'solid-js'
import { useBoards, useSession } from '../../container/ContainerContext'
import type { Board } from '../../domain/board/Board'
import type { Card } from '../../domain/board/Card'
import { createErrorReporter } from '../common/errors'
import { Modal } from '../common/Modal'
import { dateTime, describeActivity, fromLocalInput, initials, labelColor, relativeTime, toLocalInput } from '../format'
import styles from './CardModal.module.css'

export function CardModal(props: { board: Board; card: Card; onClose: () => void }) {
  const repo = useBoards()
  const me = useSession().user
  const { report, Banner } = createErrorReporter()
  const [comments, { refetch: refetchComments }] = createResource(() => repo.listComments(props.card.id))
  const [history, { refetch: refetchHistory }] = createResource(() => repo.cardActivity(props.card.id))
  const [editingDescription, setEditingDescription] = createSignal(false)

  // The board view only carries counts; load the full card (checklist) when it's opened.
  onMount(() => void report(props.board.refreshCard(props.card)))

  /** Run an action, then refresh the card's history so it reflects what just happened. */
  const act = async (action: Promise<unknown>) => {
    await report(action)
    void refetchHistory()
  }

  const canEdit = () => props.board.canEdit
  const canContribute = () => props.board.canContribute
  const list = () => props.board.listOf(props.card)

  const saveTitle = (value: string) => {
    if (value.trim() && value.trim() !== props.card.title) void act(props.board.updateCard(props.card, { title: value.trim() }))
  }

  const saveDescription = async (e: SubmitEvent) => {
    e.preventDefault()
    const text = ((e.currentTarget as HTMLFormElement).elements.namedItem('description') as HTMLTextAreaElement).value
    await act(props.board.updateCard(props.card, { description: text.trim() || null }))
    setEditingDescription(false)
  }

  const addComment = async (e: SubmitEvent) => {
    e.preventDefault()
    const area = (e.currentTarget as HTMLFormElement).elements.namedItem('body') as HTMLTextAreaElement
    if (!area.value.trim()) return
    await act(props.board.addComment(props.card, area.value.trim()))
    area.value = ''
    void refetchComments()
  }

  const addItem = async (e: SubmitEvent) => {
    e.preventDefault()
    const input = (e.currentTarget as HTMLFormElement).elements.namedItem('text') as HTMLInputElement
    if (!input.value.trim()) return
    await act(props.board.addChecklistItem(props.card, input.value.trim()))
    input.value = ''
  }

  const remove = async () => {
    if (!confirm(`Delete “${props.card.title}” permanently? Archiving keeps it recoverable.`)) return
    await report(props.board.deleteCard(props.card))
    props.onClose()
  }

  return (
    <Modal label={props.card.title} onClose={props.onClose} wide>
      <div class={styles.layout}>
        <div class={styles.main}>
          <Show when={canEdit()} fallback={<h2 class={styles.title}>{props.card.title}</h2>}>
            <input
              class={styles.titleInput}
              value={props.card.title}
              maxLength={200}
              onBlur={(e) => saveTitle(e.currentTarget.value)}
              onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.blur()}
            />
          </Show>
          <p class="muted small">
            in list <strong>{list()?.name}</strong>
            <Show when={props.card.isArchived}> · archived</Show>
          </p>

          <div class={styles.fields}>
            <label class="row">
              <input
                type="checkbox"
                checked={props.card.isCompleted}
                disabled={!canContribute()}
                onChange={(e) => act(props.board.updateCard(props.card, { completed: e.currentTarget.checked }))}
              />
              Completed
            </label>
            <label class="row">
              Due
              <input
                type="datetime-local"
                value={toLocalInput(props.card.dueAt)}
                disabled={!canEdit()}
                onChange={(e) => act(props.board.updateCard(props.card, { dueAt: fromLocalInput(e.currentTarget.value) }))}
              />
            </label>
          </div>

          <section>
            <h3>Labels</h3>
            <div class="row">
              <For each={props.board.labels} fallback={<span class="muted small">No labels on this board yet.</span>}>
                {(label) => (
                  <button
                    class={styles.toggleChip}
                    classList={{ [styles.on!]: props.card.labelIds.includes(label.id) }}
                    style={{ '--chip': labelColor(label.color) }}
                    disabled={!canEdit()}
                    onClick={() => act(props.board.toggleLabel(props.card, label.id))}
                  >
                    {label.name}
                  </button>
                )}
              </For>
            </div>
          </section>

          <section>
            <h3>Assignees</h3>
            <div class="row">
              <For each={props.board.members}>
                {(member) => (
                  <button
                    class={styles.person}
                    classList={{ [styles.on!]: props.card.assigneeIds.includes(member.userId) }}
                    // Contributors may only take a card themselves (the server enforces it too).
                    disabled={!canEdit() && !(canContribute() && member.userId === me?.id)}
                    onClick={() => act(props.board.toggleAssignee(props.card, member.userId))}
                  >
                    <span class="avatar">{initials(member.displayName)}</span>
                    {member.displayName}
                  </button>
                )}
              </For>
            </div>
          </section>

          <section>
            <h3>Description</h3>
            <Show
              when={editingDescription()}
              fallback={
                <p
                  class={styles.description}
                  classList={{ muted: !props.card.description }}
                  onClick={() => canEdit() && setEditingDescription(true)}
                >
                  {props.card.description ?? (canEdit() ? 'Add a more detailed description…' : 'No description.')}
                </p>
              }
            >
              <form class="stack" onSubmit={saveDescription}>
                <textarea name="description" rows="5" maxLength={20000} autofocus value={props.card.description ?? ''} />
                <div class="row">
                  <button class="primary">Save</button>
                  <button type="button" class="ghost" onClick={() => setEditingDescription(false)}>Cancel</button>
                </div>
              </form>
            </Show>
          </section>

          <section>
            <h3>
              Checklist <span class="muted small">{props.card.checklistDone}/{props.card.checklistTotal}</span>
            </h3>
            <div class="stack">
              <For each={props.card.checklist ?? []}>
                {(item) => (
                  <div class={styles.checkItem}>
                    <input
                      type="checkbox"
                      checked={item.doneAt !== null}
                      disabled={!canContribute()}
                      onChange={(e) => act(props.board.setChecklistItemDone(props.card, item.id, e.currentTarget.checked))}
                    />
                    <span classList={{ [styles.checked!]: item.doneAt !== null }}>{item.text}</span>
                    <Show when={canEdit()}>
                      <button class="ghost small" aria-label="Remove item" onClick={() => act(props.board.deleteChecklistItem(props.card, item.id))}>
                        ✕
                      </button>
                    </Show>
                  </div>
                )}
              </For>
              <Show when={canEdit()}>
                <form class="row" onSubmit={addItem}>
                  <input name="text" placeholder="Add an item" maxLength={500} style={{ flex: '1' }} />
                  <button>Add</button>
                </form>
              </Show>
            </div>
          </section>

          <section>
            <h3>Comments</h3>
            <Show when={canContribute()}>
              <form class="stack" onSubmit={addComment}>
                <textarea name="body" rows="2" placeholder="Write a comment…" maxLength={10000} />
                <div><button class="primary">Comment</button></div>
              </form>
            </Show>
            <div class={styles.comments}>
              <For each={comments()}>
                {(comment) => (
                  <div class={styles.comment}>
                    <span class="avatar">{initials(comment.author?.displayName ?? '?')}</span>
                    <div>
                      <div class="small">
                        <strong>{comment.author?.displayName ?? 'Deleted user'}</strong>{' '}
                        <span class="muted" title={dateTime(comment.createdAt)}>{relativeTime(comment.createdAt)}</span>
                        <Show when={comment.editedAt}><span class="muted"> (edited)</span></Show>
                      </div>
                      <p class={styles.commentBody}>{comment.body}</p>
                    </div>
                  </div>
                )}
              </For>
            </div>
          </section>
        </div>

        <aside class={styles.side}>
          <Show when={canEdit()}>
            <h3>Actions</h3>
            <button onClick={() => act(props.board.updateCard(props.card, { archived: !props.card.isArchived }))}>
              {props.card.isArchived ? 'Restore' : 'Archive'}
            </button>
            <button class="danger" onClick={remove}>Delete</button>
          </Show>
          <h3>History</h3>
          <div class={styles.history}>
            <For each={history()}>
              {(entry) => (
                <div class="small">
                  <strong>{entry.actor?.displayName ?? 'Someone'}</strong> {describeActivity(entry)}
                  <div class="muted" title={dateTime(entry.createdAt)}>{relativeTime(entry.createdAt)}</div>
                </div>
              )}
            </For>
          </div>
        </aside>
      </div>
      <Banner />
    </Modal>
  )
}
