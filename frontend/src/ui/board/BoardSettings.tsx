import { For, Show } from 'solid-js'
import type { BoardRole, LabelColor } from '../../api/dtos'
import type { Board } from '../../domain/board/Board'
import { createErrorReporter } from '../common/errors'
import { Modal } from '../common/Modal'
import { labelColor } from '../format'

const ROLES: BoardRole[] = ['viewer', 'contributor', 'editor', 'owner']
const COLORS: LabelColor[] = ['green', 'yellow', 'orange', 'red', 'purple', 'blue', 'sky', 'lime', 'pink', 'gray']

/** Members (owners manage them) and labels (editors create them). */
export function BoardSettings(props: { board: Board; onClose: () => void }) {
  const { report, Banner } = createErrorReporter()

  const addMember = async (e: SubmitEvent) => {
    e.preventDefault()
    const form = e.currentTarget as HTMLFormElement
    const data = new FormData(form)
    await report(props.board.addMember(String(data.get('email')), data.get('role') as BoardRole))
    form.reset()
  }

  const addLabel = async (e: SubmitEvent) => {
    e.preventDefault()
    const form = e.currentTarget as HTMLFormElement
    const data = new FormData(form)
    await report(props.board.createLabel(String(data.get('name')), data.get('color') as LabelColor))
    form.reset()
  }

  return (
    <Modal label="Members and labels" onClose={props.onClose}>
      <div class="stack" style={{ gap: '20px' }}>
        <section class="stack">
          <h2>Members</h2>
          <For each={props.board.members}>
            {(m) => (
              <div class="row">
                <span style={{ flex: '1' }}>
                  {m.displayName} <span class="muted small">{m.email}</span>
                </span>
                <Show when={props.board.isOwner} fallback={<span class="muted small">{m.role}</span>}>
                  <select value={m.role} onChange={(e) => report(props.board.setMemberRole(m.userId, e.currentTarget.value as BoardRole))}>
                    <For each={ROLES}>{(r) => <option value={r}>{r}</option>}</For>
                  </select>
                  <button class="ghost small" aria-label={`Remove ${m.displayName}`} onClick={() => report(props.board.removeMember(m.userId))}>
                    ✕
                  </button>
                </Show>
              </div>
            )}
          </For>
          <Show when={props.board.isOwner}>
            <form class="row" onSubmit={addMember}>
              <input name="email" type="email" placeholder="Email of an approved user" required style={{ flex: '1' }} />
              <select name="role">
                <For each={ROLES}>{(r) => <option value={r} selected={r === 'contributor'}>{r}</option>}</For>
              </select>
              <button class="primary">Add</button>
            </form>
            <p class="muted small">
              viewer: read only · contributor: move, complete, comment, take cards · editor: edit everything · owner: + members
            </p>
          </Show>
        </section>

        <section class="stack">
          <h2>Labels</h2>
          <div class="row">
            <For each={props.board.labels} fallback={<span class="muted small">None yet.</span>}>
              {(label) => <span class="label-chip" style={{ background: labelColor(label.color) }}>{label.name}</span>}
            </For>
          </div>
          <form class="row" onSubmit={addLabel}>
            <input name="name" placeholder="New label" required maxLength={50} style={{ flex: '1' }} />
            <select name="color">
              <For each={COLORS}>{(c) => <option value={c}>{c}</option>}</For>
            </select>
            <button class="primary">Create</button>
          </form>
        </section>
      </div>
      <Banner />
    </Modal>
  )
}
