import { createSignal } from 'solid-js'
import type { AuthService, User } from './AuthService'

/**
 * Who is logged in. A reactive domain object: components read `session.user` directly and
 * update when it changes. Uses only Solid's reactivity core (signals), no UI.
 */
export class Session {
  private readonly userSignal = createSignal<User | null>(null)
  private readonly readySignal = createSignal(false)

  constructor(private readonly auth: AuthService) {}

  get user(): User | null {
    return this.userSignal[0]()
  }

  /** False until we know whether a stored session is still valid (avoids flashing the login page). */
  get ready(): boolean {
    return this.readySignal[0]()
  }

  async restore(): Promise<void> {
    try {
      if (this.auth.hasSession()) this.userSignal[1](await this.auth.me())
    } catch {
      this.userSignal[1](null)
    } finally {
      this.readySignal[1](true)
    }
  }

  async login(email: string, password: string): Promise<void> {
    this.userSignal[1](await this.auth.login(email, password))
  }

  async logout(): Promise<void> {
    await this.auth.logout()
    this.userSignal[1](null)
  }

  /** The server rejected our credentials and they couldn't be renewed. */
  lost(): void {
    this.userSignal[1](null)
  }
}
