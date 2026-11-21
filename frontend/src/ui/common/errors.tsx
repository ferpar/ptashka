import { createSignal, Show } from 'solid-js'

/** A tiny error channel for a view: `report(promise)` runs an action and shows its error, if any. */
export function createErrorReporter() {
  const [message, setMessage] = createSignal<string | null>(null)
  let timer: ReturnType<typeof setTimeout> | undefined
  const show = (err: unknown) => {
    setMessage(err instanceof Error ? err.message : String(err))
    clearTimeout(timer)
    timer = setTimeout(() => setMessage(null), 6000)
  }
  const report = async <T,>(action: Promise<T>): Promise<T | undefined> => {
    try {
      return await action
    } catch (err) {
      show(err)
      return undefined
    }
  }
  const Banner = () => (
    <Show when={message()}>
      <div role="alert" class="error-banner" onClick={() => setMessage(null)}>
        {message()}
      </div>
    </Show>
  )
  return { report, show, Banner }
}

export type Report = ReturnType<typeof createErrorReporter>['report']
