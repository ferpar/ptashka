import { HttpClient } from '../api/http'
import { AuthService } from '../auth/AuthService'
import { Session } from '../auth/Session'
import { localTokenStore } from '../auth/tokenStorage'
import { HttpUserAdminRepository } from '../domain/admin/UserAdminRepository'
import { HttpBoardRepository } from '../domain/board/HttpBoardRepository'
import { HttpTokenRepository } from '../domain/tokens/TokenRepository'
import type { AppContainer } from './types'

/** Wires the app together. Plain TypeScript: no UI framework here (see ContainerContext for that). */
export function createAppContainer(): AppContainer {
  const baseUrl = import.meta.env.VITE_API_URL || ''
  // The HTTP client reports a lost session; the session is created right after (it needs auth,
  // which needs the client), so the callback looks it up when it fires.
  let session: Session | null = null
  const http = new HttpClient(baseUrl, localTokenStore, () => session?.lost())
  const auth = new AuthService(http, localTokenStore)
  session = new Session(auth)
  return {
    session,
    auth,
    boards: new HttpBoardRepository(http),
    tokens: new HttpTokenRepository(http),
    users: new HttpUserAdminRepository(http),
  }
}
