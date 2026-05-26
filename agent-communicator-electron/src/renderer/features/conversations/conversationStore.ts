import type { Message } from '../../../shared/contracts'

export function sortMessages(messages: Message[]): Message[] {
  return [...messages].sort((left, right) => left.createdAt.localeCompare(right.createdAt))
}

export function optimisticMessage(conversationKey: string, body: string): Message {
  return {
    id: `optimistic-${Date.now()}`,
    conversationKey,
    direction: 'outbound',
    author: 'you',
    recipient: conversationKey,
    body,
    createdAt: new Date().toISOString(),
    deliveryState: 'sending',
  }
}
