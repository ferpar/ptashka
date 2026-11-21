import type { AuthService } from '../auth/AuthService'
import type { Session } from '../auth/Session'
import type { BoardRepository } from '../domain/board/BoardRepository'
import type { TokenRepository } from '../domain/tokens/TokenRepository'

export interface AppContainer {
  session: Session
  auth: AuthService
  boards: BoardRepository
  tokens: TokenRepository
}
