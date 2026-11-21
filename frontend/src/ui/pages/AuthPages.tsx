import { A, Navigate, useNavigate } from '@solidjs/router'
import { createSignal, Show } from 'solid-js'
import { useAuth, useSession } from '../../container/ContainerContext'
import styles from './Pages.module.css'

export function LoginPage() {
  const session = useSession()
  const navigate = useNavigate()
  const [error, setError] = createSignal<string | null>(null)
  const [busy, setBusy] = createSignal(false)

  const submit = async (e: SubmitEvent) => {
    e.preventDefault()
    const form = new FormData(e.currentTarget as HTMLFormElement)
    setBusy(true)
    setError(null)
    try {
      await session.login(String(form.get('email')), String(form.get('password')))
      navigate('/')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Show when={!session.user} fallback={<Navigate href="/" />}>
      <div class={styles.authPage}>
        <form class={styles.authCard} onSubmit={submit}>
          <h1>Log in to Ptashka</h1>
          <label>Email<input name="email" type="email" autocomplete="username" required /></label>
          <label>Password<input name="password" type="password" autocomplete="current-password" required /></label>
          <Show when={error()}><p class="error">{error()}</p></Show>
          <button class="primary" disabled={busy()}>{busy() ? 'Logging in…' : 'Log in'}</button>
          <p class="muted small">No account yet? <A href="/register">Sign up</A></p>
        </form>
      </div>
    </Show>
  )
}

export function RegisterPage() {
  const auth = useAuth()
  const [error, setError] = createSignal<string | null>(null)
  const [done, setDone] = createSignal(false)

  const submit = async (e: SubmitEvent) => {
    e.preventDefault()
    const form = new FormData(e.currentTarget as HTMLFormElement)
    setError(null)
    try {
      await auth.register(String(form.get('email')), String(form.get('password')), String(form.get('name')))
      setDone(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <div class={styles.authPage}>
      <Show
        when={!done()}
        fallback={
          <div class={styles.authCard}>
            <h1>Almost there</h1>
            <p>Your account was created. An admin needs to approve it before you can log in.</p>
            <A href="/login">Back to log in</A>
          </div>
        }
      >
        <form class={styles.authCard} onSubmit={submit}>
          <h1>Create an account</h1>
          <label>Name<input name="name" required maxLength={100} /></label>
          <label>Email<input name="email" type="email" autocomplete="username" required /></label>
          <label>
            Password
            <input name="password" type="password" autocomplete="new-password" required minLength={8} maxLength={72} />
          </label>
          <Show when={error()}><p class="error">{error()}</p></Show>
          <button class="primary">Sign up</button>
          <p class="muted small">Already have one? <A href="/login">Log in</A></p>
        </form>
      </Show>
    </div>
  )
}
