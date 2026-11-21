import type { AuthResponseDTO, UserDTO } from '../api/dtos'
import { ApiError, type HttpClient } from '../api/http'
import type { localTokenStore } from './tokenStorage'

export interface User {
  id: number
  email: string
  displayName: string
  isAdmin: boolean
}

export const toUser = (dto: UserDTO): User => ({
  id: dto.id,
  email: dto.email,
  displayName: dto.display_name,
  isAdmin: dto.role === 'admin',
})

/** Login, registration and logout against /api/auth. Framework-free. */
export class AuthService {
  constructor(
    private readonly http: HttpClient,
    private readonly tokens: typeof localTokenStore,
  ) {}

  hasSession(): boolean {
    return this.tokens.refresh() !== null
  }

  async login(email: string, password: string): Promise<User> {
    try {
      const { user, tokens } = await this.http.post<AuthResponseDTO>('/api/auth/login', { email, password })
      this.tokens.set(tokens.access_token, tokens.refresh_token)
      return toUser(user)
    } catch (err) {
      if (err instanceof ApiError && err.message === 'account_pending') {
        throw new Error('Your account is waiting for an admin to approve it.')
      }
      if (err instanceof ApiError && err.message === 'account_disabled') {
        throw new Error('This account has been disabled.')
      }
      throw err
    }
  }

  async register(email: string, password: string, displayName: string): Promise<void> {
    await this.http.post('/api/auth/register', { email, password, display_name: displayName })
  }

  async me(): Promise<User> {
    return toUser(await this.http.get<UserDTO>('/api/auth/me'))
  }

  async logout(): Promise<void> {
    const refresh = this.tokens.refresh()
    this.tokens.clear()
    if (refresh) await this.http.post('/api/auth/logout', { refresh_token: refresh }).catch(() => undefined)
  }
}
