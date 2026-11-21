import type { ApiTokenCreatedDTO, ApiTokenDTO, TokenScope } from '../../api/dtos'
import type { HttpClient } from '../../api/http'

export interface ApiToken {
  id: number
  name: string
  prefix: string
  scope: TokenScope
  createdAt: Date
  lastUsedAt: Date | null
  expiresAt: Date | null
  revokedAt: Date | null
}

const toToken = (dto: ApiTokenDTO): ApiToken => ({
  id: dto.id,
  name: dto.name,
  prefix: dto.prefix,
  scope: dto.scope,
  createdAt: new Date(dto.created_at),
  lastUsedAt: dto.last_used_at ? new Date(dto.last_used_at) : null,
  expiresAt: dto.expires_at ? new Date(dto.expires_at) : null,
  revokedAt: dto.revoked_at ? new Date(dto.revoked_at) : null,
})

export interface TokenRepository {
  list(): Promise<ApiToken[]>
  /** Returns the token and its secret, which is never shown again. */
  create(name: string, scope: TokenScope, expiresInDays: number | null): Promise<{ token: ApiToken; secret: string }>
  revoke(id: number): Promise<void>
}

export class HttpTokenRepository implements TokenRepository {
  constructor(private readonly http: HttpClient) {}

  async list() {
    return (await this.http.get<{ tokens: ApiTokenDTO[] }>('/api/tokens')).tokens.map(toToken)
  }
  async create(name: string, scope: TokenScope, expiresInDays: number | null) {
    const dto = await this.http.post<ApiTokenCreatedDTO>('/api/tokens', { name, scope, expires_in_days: expiresInDays })
    return { token: toToken(dto), secret: dto.token }
  }
  async revoke(id: number) {
    await this.http.delete(`/api/tokens/${id}`)
  }
}
