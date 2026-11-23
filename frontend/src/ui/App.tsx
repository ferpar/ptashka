import { Navigate, Route, Router } from '@solidjs/router'
import { Show, type ParentProps } from 'solid-js'
import { useSession } from '../container/ContainerContext'
import { BoardPage } from './board/BoardPage'
import { Layout } from './Layout'
import { AdminPage } from './pages/AdminPage'
import { LoginPage, RegisterPage } from './pages/AuthPages'
import { BoardsPage } from './pages/BoardsPage'
import { MyTasksPage } from './pages/MyTasksPage'
import { TokensPage } from './pages/TokensPage'

/** Pages behind login: wait until we know whether the stored session is valid, then decide. */
function RequireAuth(props: ParentProps) {
  const session = useSession()
  return (
    <Show when={session.ready} fallback={<p class="muted" style={{ padding: '24px' }}>Loading…</p>}>
      <Show when={session.user} fallback={<Navigate href="/login" />}>
        <Layout>{props.children}</Layout>
      </Show>
    </Show>
  )
}

/** Hides admin pages from everyone else. Only a convenience: the server checks every admin request. */
function RequireAdmin(props: ParentProps) {
  const session = useSession()
  return (
    <Show when={session.user?.isAdmin} fallback={<Navigate href="/" />}>
      {props.children}
    </Show>
  )
}

export function App() {
  void useSession().restore()
  return (
    <Router>
      <Route path="/login" component={LoginPage} />
      <Route path="/register" component={RegisterPage} />
      <Route path="/" component={RequireAuth}>
        <Route path="/" component={BoardsPage} />
        <Route path="/boards/:id" component={BoardPage} />
        <Route path="/my-tasks" component={MyTasksPage} />
        <Route path="/tokens" component={TokensPage} />
        <Route path="/admin" component={() => <RequireAdmin><AdminPage /></RequireAdmin>} />
      </Route>
    </Router>
  )
}
