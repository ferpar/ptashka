/**
 * The only container file that knows about Solid: it hands the (framework-free) container to
 * components. Tests can inject a container built with fakes.
 */
import { createContext, useContext, type ParentProps } from 'solid-js'
import { createAppContainer } from './AppContainer'
import type { AppContainer } from './types'

const ContainerCtx = createContext<AppContainer>()

export function ContainerProvider(props: ParentProps<{ container?: AppContainer }>) {
  // Components run once in Solid, so this builds the container exactly once (no useRef needed).
  const container = props.container ?? createAppContainer()
  return <ContainerCtx.Provider value={container}>{props.children}</ContainerCtx.Provider>
}

export function useContainer(): AppContainer {
  const container = useContext(ContainerCtx)
  if (!container) throw new Error('useContainer must be used within a ContainerProvider')
  return container
}

export const useSession = () => useContainer().session
export const useAuth = () => useContainer().auth
export const useBoards = () => useContainer().boards
export const useTokens = () => useContainer().tokens
