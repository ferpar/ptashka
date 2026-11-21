/**
 * The HTTP client: JSON in and out, a hard timeout, the access token on every request,
 * and one transparent refresh when the server says 401. Framework-free.
 */

export const DEFAULT_TIMEOUT_MS = 15_000

/** An HTTP error that remembers its status code (null: no response at all). */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number | null,
    readonly detail: unknown = null,
  ) {
    super(message)
    this.name = 'ApiError'
  }

  get isConflict(): boolean {
    return this.status === 409
  }
}

/** The API's `detail` comes in three shapes: a string, an object with `message`, or 422 field errors. */
function messageFrom(detail: unknown, fallback: string): string {
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object' && 'message' in detail && typeof detail.message === 'string') {
    return detail.message
  }
  if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg)
  return fallback
}

export interface TokenStore {
  access(): string | null
  refresh(): string | null
  setAccess(token: string): void
  clear(): void
}

type Query = Record<string, string | number | boolean | null | undefined>

export class HttpClient {
  private refreshing: Promise<boolean> | null = null

  constructor(
    private readonly baseUrl: string,
    private readonly tokens: TokenStore,
    /** Called when the session can't be renewed (refresh token missing, expired or revoked). */
    private readonly onAuthLost: () => void,
  ) {}

  get<T>(path: string, query?: Query): Promise<T> {
    return this.request<T>('GET', path, undefined, query)
  }
  post<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>('POST', path, body)
  }
  patch<T>(path: string, body: unknown): Promise<T> {
    return this.request<T>('PATCH', path, body)
  }
  put<T = void>(path: string): Promise<T> {
    return this.request<T>('PUT', path)
  }
  delete<T = void>(path: string): Promise<T> {
    return this.request<T>('DELETE', path)
  }

  async request<T>(method: string, path: string, body?: unknown, query?: Query): Promise<T> {
    let response = await this.send(method, path, body, query)
    if (response.status === 401 && this.tokens.refresh()) {
      if (await this.renew()) {
        response = await this.send(method, path, body, query)
      } else {
        this.tokens.clear()
        this.onAuthLost()
      }
    }
    if (!response.ok) {
      const data = await response.json().catch(() => ({}))
      throw new ApiError(messageFrom(data.detail, `Request failed (${response.status})`), response.status, data.detail)
    }
    if (response.status === 204) return undefined as T
    return (await response.json()) as T
  }

  /** One refresh at a time: if five requests get a 401 together, they share a single renewal. */
  private renew(): Promise<boolean> {
    this.refreshing ??= (async () => {
      try {
        const response = await this.send('POST', '/api/auth/refresh', { refresh_token: this.tokens.refresh() }, undefined, false)
        if (!response.ok) return false
        this.tokens.setAccess((await response.json()).access_token)
        return true
      } catch {
        return false
      } finally {
        this.refreshing = null
      }
    })()
    return this.refreshing
  }

  private async send(method: string, path: string, body: unknown, query: Query | undefined, auth = true): Promise<Response> {
    const url = new URL(this.baseUrl + path, window.location.origin)
    for (const [key, value] of Object.entries(query ?? {})) {
      if (value !== undefined && value !== null && value !== '') url.searchParams.set(key, String(value))
    }
    const headers: Record<string, string> = {}
    if (body !== undefined) headers['Content-Type'] = 'application/json'
    const access = this.tokens.access()
    if (auth && access) headers.Authorization = `Bearer ${access}`

    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS)
    try {
      return await fetch(url, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
      })
    } catch (err) {
      throw new ApiError(controller.signal.aborted ? 'The server took too long to answer' : 'Could not reach the server', null)
    } finally {
      clearTimeout(timer)
    }
  }
}
