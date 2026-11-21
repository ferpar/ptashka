import { onCleanup, onMount, type ParentProps } from 'solid-js'
import { Portal } from 'solid-js/web'
import styles from './Modal.module.css'

/** A dialog over the page: closes on Escape or a click outside. */
export function Modal(props: ParentProps<{ onClose: () => void; wide?: boolean; label: string }>) {
  const onKey = (e: KeyboardEvent) => e.key === 'Escape' && props.onClose()
  onMount(() => document.addEventListener('keydown', onKey))
  onCleanup(() => document.removeEventListener('keydown', onKey))
  return (
    <Portal>
      <div class={styles.backdrop} onClick={(e) => e.target === e.currentTarget && props.onClose()}>
        <div class={styles.dialog} classList={{ [styles.wide!]: props.wide }} role="dialog" aria-label={props.label}>
          <button class={`ghost ${styles.close}`} aria-label="Close" onClick={() => props.onClose()}>
            ✕
          </button>
          {props.children}
        </div>
      </div>
    </Portal>
  )
}
