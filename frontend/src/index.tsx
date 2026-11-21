import { render } from 'solid-js/web'
import './styles/global.css'
import { ContainerProvider } from './container/ContainerContext'
import { App } from './ui/App'

render(
  () => (
    <ContainerProvider>
      <App />
    </ContainerProvider>
  ),
  document.getElementById('root')!,
)
