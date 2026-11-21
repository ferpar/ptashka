/**
 * Short names for the API's wire types, generated from the backend's OpenAPI schema
 * (`npm run gen:api`). These are snake_case DTOs: only repositories and mappers touch them;
 * the rest of the app works with domain types.
 */
import type { components } from './schema'

type Schemas = components['schemas']

export type UserDTO = Schemas['UserSchema']
export type UserPublicDTO = Schemas['UserPublic']
export type AuthResponseDTO = Schemas['AuthResponse']
export type BoardSummaryDTO = Schemas['BoardSummary']
export type BoardDetailDTO = Schemas['BoardDetail']
export type ListDTO = Schemas['ListSchema']
export type ListWithCardsDTO = Schemas['ListWithCards']
export type MemberDTO = Schemas['MemberSchema']
export type LabelDTO = Schemas['LabelSchema']
export type CardDTO = Schemas['CardSchema']
export type CardDetailDTO = Schemas['CardDetail']
export type CardSearchHitDTO = Schemas['CardSearchHit']
export type CardSearchResponseDTO = Schemas['CardSearchResponse']
export type ChecklistItemDTO = Schemas['ChecklistItemSchema']
export type CommentDTO = Schemas['CommentSchema']
export type ActivityDTO = Schemas['ActivitySchema']
export type ActivityPageDTO = Schemas['ActivityPage']
export type ApiTokenDTO = Schemas['ApiTokenSchema']
export type ApiTokenCreatedDTO = Schemas['ApiTokenCreated']

export type BoardRole = Schemas['BoardRole']
export type LabelColor = Schemas['LabelColor']
export type TokenScope = Schemas['TokenScope']
export type ActivityKind = Schemas['ActivityKind']
