import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, HttpClient, type TokenStore } from '../http'

function memoryTokens(access: string | null, refresh: string | null): TokenStore & { a: string | null } {
  const store = {
    a: access,
    access: () => store.a,
    refresh: () => refresh,
    setAccess: (t: string) => { store.a = t },
    clear: () => { store.a = null; refresh = null },
  }
  return store
}

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

afterEach(() => vi.unstubAllGlobals())

describe('HttpClient', () => {
  it('renews an expired access token once and retries', async () => {
    const tokens = memoryTokens('old', 'refresh-me')
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(json(401, { detail: 'expired' }))
      .mockResolvedValueOnce(json(200, { access_token: 'new' }))
      .mockResolvedValueOnce(json(200, { ok: true }))
    vi.stubGlobal('fetch', fetchMock)

    const result = await new HttpClient('', tokens, () => {}).get<{ ok: boolean }>('/api/boards')
    expect(result).toEqual({ ok: true })
    expect(tokens.a).toBe('new')
    const retried = fetchMock.mock.calls[2][1] as RequestInit
    expect((retried.headers as Record<string, string>).Authorization).toBe('Bearer new')
  })

  it('shares one renewal between simultaneous 401s', async () => {
    const tokens = memoryTokens('old', 'refresh-me')
    let refreshes = 0
    vi.stubGlobal('fetch', vi.fn(async (url: URL, init: RequestInit) => {
      if (url.pathname === '/api/auth/refresh') { refreshes++; return json(200, { access_token: 'new' }) }
      const auth = (init.headers as Record<string, string>).Authorization
      return auth === 'Bearer new' ? json(200, {}) : json(401, {})
    }))
    const http = new HttpClient('', tokens, () => {})
    await Promise.all([http.get('/a'), http.get('/b'), http.get('/c')])
    expect(refreshes).toBe(1)
  })

  it('reports a lost session when renewal fails', async () => {
    const tokens = memoryTokens('old', 'revoked')
    const lost = vi.fn()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(json(401, {})).mockResolvedValueOnce(json(401, {})))
    await expect(new HttpClient('', tokens, lost).get('/api/boards')).rejects.toBeInstanceOf(ApiError)
    expect(lost).toHaveBeenCalledOnce()
    expect(tokens.refresh()).toBeNull()
  })

  it('reads the API\'s three error shapes', async () => {
    const tokens = memoryTokens('t', null)
    const http = new HttpClient('', tokens, () => {})
    for (const [detail, message] of [
      ['Board not found', 'Board not found'],
      [{ message: 'Card was modified', current_version: 2 }, 'Card was modified'],
      [[{ msg: 'Field required' }], 'Field required'],
    ] as const) {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(json(422, { detail })))
      await expect(http.get('/x')).rejects.toThrow(message)
    }
  })
})
