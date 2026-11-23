import { fireEvent, render, screen, within } from '@solidjs/testing-library'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { UserRole, UserStatus } from '../../api/dtos'
import type { AuthService, User } from '../../auth/AuthService'
import { Session } from '../../auth/Session'
import { ContainerProvider } from '../../container/ContainerContext'
import type { AppContainer } from '../../container/types'
import type { Account, UserAdminRepository } from '../../domain/admin/UserAdminRepository'
import { AdminPage } from '../pages/AdminPage'

const account = (id: number, status: UserStatus, role: UserRole = 'user'): Account => ({
  id,
  email: `user${id}@example.com`,
  displayName: `User ${id}`,
  role,
  status,
  createdAt: new Date(),
})

/** Behaves like the server: saves the change and returns the saved account. */
class FakeUserAdminRepository implements UserAdminRepository {
  updates: { id: number; changes: object }[] = []
  failWith: string | null = null
  constructor(public accounts: Account[]) {}

  async list() {
    return this.accounts
  }
  async update(id: number, changes: { status?: UserStatus; role?: UserRole }) {
    if (this.failWith) throw new Error(this.failWith)
    this.updates.push({ id, changes })
    const saved = { ...this.accounts.find((a) => a.id === id)!, ...changes }
    this.accounts = this.accounts.map((a) => (a.id === id ? saved : a))
    return saved
  }
}

async function renderPage(repo: FakeUserAdminRepository) {
  const me: User = { id: 1, email: 'user1@example.com', displayName: 'User 1', isAdmin: true }
  const session = new Session({ login: async () => me } as unknown as AuthService)
  await session.login('', '')
  // Only what this page uses; the rest of the container never gets touched.
  const container = { session, users: repo } as unknown as AppContainer
  render(() => (
    <ContainerProvider container={container}>
      <AdminPage />
    </ContainerProvider>
  ))
  await screen.findByTestId('account-1')
}

afterEach(() => vi.restoreAllMocks())

describe('AdminPage', () => {
  it('approves a pending account and shows it as the server saved it', async () => {
    const repo = new FakeUserAdminRepository([account(1, 'active', 'admin'), account(2, 'pending')])
    await renderPage(repo)

    const box = screen.getByRole('region', { name: 'Waiting for approval' })
    fireEvent.click(within(box).getByRole('button', { name: 'Approve' }))

    expect(await screen.findByText('active', { selector: `[data-testid="account-2"] span` })).toBeInTheDocument()
    expect(repo.updates).toEqual([{ id: 2, changes: { status: 'active' } }])
    // Nobody is waiting any more, so the box goes away.
    expect(screen.queryByRole('region', { name: 'Waiting for approval' })).not.toBeInTheDocument()
  })

  it('offers no actions on your own account', async () => {
    await renderPage(new FakeUserAdminRepository([account(1, 'active', 'admin'), account(2, 'active')]))

    expect(within(screen.getByTestId('account-1')).queryAllByRole('button')).toHaveLength(0)
    expect(screen.getByTestId('account-1')).toHaveTextContent('you')
    expect(within(screen.getByTestId('account-2')).getByRole('button', { name: 'Disable' })).toBeInTheDocument()
  })

  it('asks before disabling, and does nothing when you cancel', async () => {
    const repo = new FakeUserAdminRepository([account(1, 'active', 'admin'), account(2, 'active')])
    await renderPage(repo)
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)

    fireEvent.click(within(screen.getByTestId('account-2')).getByRole('button', { name: 'Disable' }))

    expect(confirm).toHaveBeenCalledWith(expect.stringContaining('user2@example.com'))
    expect(repo.updates).toEqual([])
  })

  it('shows the server refusing, and leaves the account as it was', async () => {
    const repo = new FakeUserAdminRepository([account(1, 'active', 'admin'), account(2, 'active')])
    await renderPage(repo)
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    repo.failWith = 'Admin access required'

    fireEvent.click(within(screen.getByTestId('account-2')).getByRole('button', { name: 'Make admin' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Admin access required')
    expect(screen.getByTestId('account-2')).toHaveTextContent('user')
    expect(within(screen.getByTestId('account-2')).getByRole('button', { name: 'Make admin' })).toBeEnabled()
  })
})
