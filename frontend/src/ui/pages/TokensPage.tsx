import { createResource, createSignal, For, Show } from 'solid-js'
import type { TokenScope } from '../../api/dtos'
import { useTokens } from '../../container/ContainerContext'
import { createErrorReporter } from '../common/errors'
import { relativeTime, shortDate } from '../format'
import styles from './Pages.module.css'

/** Personal API tokens, for scripts and agents. */
export function TokensPage() {
  const repo = useTokens()
  const { report, Banner } = createErrorReporter()
  const [tokens, { refetch }] = createResource(() => repo.list())
  const [secret, setSecret] = createSignal<string | null>(null)
  const [copied, setCopied] = createSignal(false)

  const create = async (e: SubmitEvent) => {
    e.preventDefault()
    const form = e.currentTarget as HTMLFormElement
    const data = new FormData(form)
    const days = Number(data.get('days'))
    const created = await report(repo.create(String(data.get('name')), data.get('scope') as TokenScope, days > 0 ? days : null))
    if (created) {
      setSecret(created.secret)
      setCopied(false)
      form.reset()
      void refetch()
    }
  }

  const copy = async () => {
    await navigator.clipboard.writeText(secret() ?? '')
    setCopied(true)
  }

  return (
    <div class={styles.page}>
      <h1>API tokens</h1>
      <p class="muted">
        For scripts and agents. A token acts as you, limited by its scope: <strong>read</strong> can only look,{' '}
        <strong>write</strong> can do whatever your board roles allow.
      </p>

      <Show when={secret()}>
        <div class={styles.secret}>
          <strong>Copy your new token now. It won't be shown again.</strong>
          <code>{secret()}</code>
          <div class="row">
            <button class="primary" onClick={copy}>{copied() ? 'Copied' : 'Copy'}</button>
            <button class="ghost" onClick={() => setSecret(null)}>Done</button>
          </div>
        </div>
      </Show>

      <form class={`row ${styles.tokenForm}`} onSubmit={create}>
        <input name="name" placeholder="What is it for? e.g. Research agent" required maxLength={100} />
        <select name="scope">
          <option value="read">read</option>
          <option value="write">write</option>
        </select>
        <select name="days">
          <option value="0">never expires</option>
          <option value="30">30 days</option>
          <option value="90">90 days</option>
          <option value="365">1 year</option>
        </select>
        <button class="primary">Create token</button>
      </form>

      <table class={styles.table}>
        <thead>
          <tr><th>Name</th><th>Token</th><th>Scope</th><th>Last used</th><th>Expires</th><th /></tr>
        </thead>
        <tbody>
          <For each={tokens()} fallback={<tr><td colSpan={6} class="muted">No tokens yet.</td></tr>}>
            {(token) => (
              <tr classList={{ [styles.revoked!]: token.revokedAt !== null }}>
                <td>{token.name}</td>
                <td><code>{token.prefix}…</code></td>
                <td>{token.scope}</td>
                <td class="muted">{token.lastUsedAt ? relativeTime(token.lastUsedAt) : 'never'}</td>
                <td class="muted">{token.expiresAt ? shortDate(token.expiresAt) : 'never'}</td>
                <td>
                  <Show when={!token.revokedAt} fallback={<span class="muted small">revoked</span>}>
                    <button class="danger small" onClick={async () => { await report(repo.revoke(token.id)); void refetch() }}>
                      Revoke
                    </button>
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
