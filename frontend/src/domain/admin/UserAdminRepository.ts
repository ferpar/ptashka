import type { AdminUserUpdateDTO, UserDTO, UserListDTO, UserRole, UserStatus } from '../../api/dtos'
import type { HttpClient } from '../../api/http'

/** An account as a site admin sees it (unlike `auth/User`, which is "who am I"). */
export interface Account {
  id: number
  email: string
  displayName: string
  role: UserRole
  status: UserStatus
  createdAt: Date
}

export const toAccount = (dto: UserDTO): Account => ({
  id: dto.id,
  email: dto.email,
  displayName: dto.display_name,
  role: dto.role,
  status: dto.status,
  createdAt: new Date(dto.created_at),
})

/** Approving, disabling and promoting accounts. The server enforces who may (site admins only). */
export interface UserAdminRepository {
  /** Newest first. */
  list(): Promise<Account[]>
  /** Returns the account as the server saved it. */
  update(id: number, changes: { status?: UserStatus; role?: UserRole }): Promise<Account>
}

export class HttpUserAdminRepository implements UserAdminRepository {
  constructor(private readonly http: HttpClient) {}

  async list() {
    return (await this.http.get<UserListDTO>('/api/admin/users')).users.map(toAccount)
  }
  async update(id: number, changes: AdminUserUpdateDTO) {
    return toAccount(await this.http.patch<UserDTO>(`/api/admin/users/${id}`, changes))
  }
}
