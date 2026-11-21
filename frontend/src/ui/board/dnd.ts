/**
 * Drag and drop with Pragmatic drag and drop (framework-independent, built for Trello-like boards).
 * Solid glue: attach on mount, detach on cleanup. Drops are handled in one place (the board's
 * monitor), which turns "dropped on card X, near its top/bottom edge" into "move after card Y".
 */
import { combine } from '@atlaskit/pragmatic-drag-and-drop/combine'
import { draggable, dropTargetForElements, monitorForElements } from '@atlaskit/pragmatic-drag-and-drop/element/adapter'
import { attachClosestEdge } from '@atlaskit/pragmatic-drag-and-drop-hitbox/closest-edge/attach-closest-edge'
import { extractClosestEdge } from '@atlaskit/pragmatic-drag-and-drop-hitbox/closest-edge/extract-closest-edge'
import type { Edge } from '@atlaskit/pragmatic-drag-and-drop-hitbox/types'
import type { Board } from '../../domain/board/Board'
import type { Card } from '../../domain/board/Card'
import type { BoardList } from '../../domain/board/BoardList'

type CardDrag = { type: 'card'; cardId: number }
const isCardDrag = (data: Record<string | symbol, unknown>): data is CardDrag => data.type === 'card'

/** Make a card tile draggable and a drop target; reports which edge the pointer is near. */
export function cardDnd(element: HTMLElement, card: Card, onEdge: (edge: Edge | null) => void): () => void {
  return combine(
    draggable({ element, getInitialData: (): CardDrag => ({ type: 'card', cardId: card.id }) }),
    dropTargetForElements({
      element,
      canDrop: ({ source }) => isCardDrag(source.data) && source.data.cardId !== card.id,
      getData: ({ input }) =>
        attachClosestEdge({ type: 'card-target', cardId: card.id }, { element, input, allowedEdges: ['top', 'bottom'] }),
      onDrag: ({ self }) => onEdge(extractClosestEdge(self.data)),
      onDragLeave: () => onEdge(null),
      onDrop: () => onEdge(null),
    }),
  )
}

/** A list's body: dropping on empty space puts the card at the bottom. */
export function listDropTarget(element: HTMLElement, list: BoardList, onOver: (over: boolean) => void): () => void {
  return dropTargetForElements({
    element,
    canDrop: ({ source }) => isCardDrag(source.data),
    getData: () => ({ type: 'list-target', listId: list.id }),
    onDragEnter: () => onOver(true),
    onDragLeave: () => onOver(false),
    onDrop: () => onOver(false),
  })
}

/** Watch every card drop on the board and turn it into a Board.moveCard call. */
export function monitorCardDrops(board: Board, move: (card: Card, to: BoardList, after: Card | null) => void): () => void {
  return monitorForElements({
    canMonitor: ({ source }) => isCardDrag(source.data),
    onDrop: ({ source, location }) => {
      const target = location.current.dropTargets[0] // The innermost target: a card, else a list.
      if (!target || !isCardDrag(source.data)) return
      const card = board.card(source.data.cardId)
      if (!card) return

      if (target.data.type === 'card-target') {
        const onto = board.card(target.data.cardId as number)
        const list = onto && board.listOf(onto)
        if (!onto || !list) return
        const siblings = list.cards.filter((c) => c !== card)
        const index = siblings.indexOf(onto)
        // Near the top edge: goes before `onto`, i.e. after the card before it.
        const after = extractClosestEdge(target.data) === 'top' ? (siblings[index - 1] ?? null) : onto
        move(card, list, after)
      } else if (target.data.type === 'list-target') {
        const list = board.lists.find((l) => l.id === target.data.listId)
        if (!list) return
        const siblings = list.cards.filter((c) => c !== card)
        move(card, list, siblings[siblings.length - 1] ?? null)
      }
    },
  })
}
