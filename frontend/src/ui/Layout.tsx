import { A, useNavigate } from '@solidjs/router'
import { Show, type ParentProps } from 'solid-js'
import { useSession } from '../container/ContainerContext'
import { initials } from './format'
import styles from './Layout.module.css'

export function Layout(props: ParentProps) {
  const session = useSession()
  const navigate = useNavigate()
  const logout = async () => {
    await session.logout()
    navigate('/login')
  }
  return (
    <div class={styles.shell}>
      <header class={styles.header}>
        <A href="/" class={styles.brand}>
          <img src="/favicon.svg" alt="" width="22" height="22" /> Ptashka
        </A>
        <nav class={styles.nav}>
          <A href="/" end activeClass={styles.active}>Boards</A>
          <A href="/my-tasks" activeClass={styles.active}>My tasks</A>
          <A href="/tokens" activeClass={styles.active}>API tokens</A>
          <Show when={session.user?.isAdmin}>
            <A href="/admin" activeClass={styles.active}>Admin</A>
          </Show>
        </nav>
        <div class={styles.user}>
          <span class="avatar" title={session.user?.email}>{initials(session.user?.displayName ?? '')}</span>
          <span class={styles.userName}>{session.user?.displayName}</span>
          <button class="ghost small" onClick={logout}>Log out</button>
        </div>
      </header>
      <main class={styles.main}>{props.children}</main>
    </div>
  )
}
