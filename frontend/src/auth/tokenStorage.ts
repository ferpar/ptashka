import type { TokenStore } from '../api/http'

const ACCESS = 'ptashka.access_token'
const REFRESH = 'ptashka.refresh_token'

/** Tokens in localStorage, so a reload keeps you logged in. */
export const localTokenStore: TokenStore & { set(access: string, refresh: string): void } = {
  access: () => localStorage.getItem(ACCESS),
  refresh: () => localStorage.getItem(REFRESH),
  setAccess: (token) => localStorage.setItem(ACCESS, token),
  set(access, refresh) {
    localStorage.setItem(ACCESS, access)
    localStorage.setItem(REFRESH, refresh)
  },
  clear() {
    localStorage.removeItem(ACCESS)
    localStorage.removeItem(REFRESH)
  },
}
