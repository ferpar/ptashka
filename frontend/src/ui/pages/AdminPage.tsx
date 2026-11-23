import { createResource, createSignal, For, Show } from 'solid-js'
import type { UserRole, UserStatus } from '../../api/dtos'
import { useSession, useUserAdmin } from '../../container/ContainerContext'
import type { Account } from '../../domain/admin/UserAdminRepository'
import { createErrorReporter } from '../common/errors'
import { relativeTime } from '../format'
import styles from './Pages.module.css'

/**
 * Site administration: approve new accounts, disable or re-enable them, grant or remove admin.
 * Only reachable by admins (App.tsx), but that's a convenience: the server refuses everyone else.
 */
export function AdminPage() {
  const repo = useUserAdmin()
  const session = useSession()
  const { report, Banner } = createErrorReporter()
  const [accounts, { mutate }] = createResource(() => repo.list())
  const [busy, setBusy] = createSignal<number | null>(null)

  const pending = () => (accounts() ?? []).filter((a) => a.status === 'pending')
  const isMe = (account: Account) => account.id === session.user?.id

  /** Apply a change, then show the account exactly as the server saved it. */
  const change = async (account: Account, changes: { status?: UserStatus; role?: UserRole }, confirmText?: string) => {
    if (confirmText && !window.confirm(confirmText)) return
    setBusy(account.id)
    const saved = await report(repo.update(account.id, changes))
    setBusy(null)
    if (saved) mutate((list) => list?.map((a) => (a.id === saved.id ? saved : a)))
  }

  const approve = (a: Account) => change(a, { status: 'active' })
  const disable = (a: Account) =>
    change(a, { status: 'disabled' }, `Disable ${a.email}? They are signed out everywhere and can't log in until re-enabled.`)
  const reject = (a: Account) => change(a, { status: 'disabled' }, `Reject ${a.email}? The account stays, disabled.`)
  const enable = (a: Account) => change(a, { status: 'active' })
  const makeAdmin = (a: Account) =>
    change(a, { role: 'admin' }, `Make ${a.email} an admin? Admins can approve, disable and promote anyone.`)
  const removeAdmin = (a: Account) => change(a, { role: 'user' })

  return (
    <div class={styles.page}>
      <h1>Accounts</h1>

      <Show when={pending().length > 0}>
        <section class={styles.pendingBox} aria-label="Waiting for approval">
          <h2>Waiting for approval ({pending().length})</h2>
          <For each={pending()}>
            {(account) => (
              <div class={styles.pendingRow} data-testid={`pending-${account.id}`}>
                <div class={styles.who}>
                  <strong>{account.displayName}</strong>
                  <span class="muted">{account.email}</span>
                  <span class="muted small">registered {relativeTime(account.createdAt)}</span>
                </div>
                <div class="row">
                  <button class="primary" disabled={busy() === account.id} onClick={() => approve(account)}>Approve</button>
                  <button class="danger" disabled={busy() === account.id} onClick={() => reject(account)}>Reject</button>
                </div>
              </div>
            )}
          </For>
        </section>
      </Show>

      <table class={styles.table}>
        <thead>
          <tr><th>Name</th><th>Email</th><th>Status</th><th>Role</th><th>Registered</th><th /></tr>
        </thead>
        <tbody>
          <For each={accounts()} fallback={<tr><td colSpan={6} class="muted">{accounts.loading ? 'Loading…' : 'No accounts.'}</td></tr>}>
            {(account) => (
              <tr data-testid={`account-${account.id}`} classList={{ [styles.revoked!]: account.status === 'disabled' }}>
                <td>{account.displayName}</td>
                <td>{account.email}</td>
                <td><span class={`${styles.status} ${styles[account.status]}`}>{account.status}</span></td>
                <td>{account.role}</td>
                <td class="muted">{relativeTime(account.createdAt)}</td>
                <td>
                  {/* You can't lock yourself out (the server refuses too), so no buttons on your own row. */}
                  <Show when={!isMe(account)} fallback={<span class="muted small">you</span>}>
                    <div class="row">
                      <Show when={account.status === 'pending'}>
                        <button class="small" disabled={busy() === account.id} onClick={() => approve(account)}>Approve</button>
                      </Show>
                      <Show when={account.status === 'active'}>
                        <button class="danger small" disabled={busy() === account.id} onClick={() => disable(account)}>Disable</button>
                      </Show>
                      <Show when={account.status === 'disabled'}>
                        <button class="small" disabled={busy() === account.id} onClick={() => enable(account)}>Enable</button>
                      </Show>
                      <Show
                        when={account.role === 'admin'}
                        fallback={<button class="ghost small" disabled={busy() === account.id} onClick={() => makeAdmin(account)}>Make admin</button>}
                      >
                        <button class="ghost small" disabled={busy() === account.id} onClick={() => removeAdmin(account)}>Remove admin</button>
                      </Show>
                    </div>
                  </Show>
                </td>
              </tr>
            )}
          </For>
        </tbody>
      </table>
      <Banner />
    </div>
  )
}
