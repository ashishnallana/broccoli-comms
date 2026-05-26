import type { Message } from '../../shared/contracts'
import { formatTime } from '../lib/time'

interface Props {
  message: Message
}

export function MessageBubble({ message }: Props) {
  const kind = message.direction === 'outbound' ? 'you' : message.direction === 'inbound' ? 'agent' : 'system'

  return (
    <article className={`msg ${kind} ${message.deliveryState}`}>
      <div className="msg-head">
        <span className="msg-from">{message.direction === 'outbound' ? 'you' : message.author}</span>
        <span className={`msg-flag ${message.deliveryState}`}>{message.deliveryState}</span>
      </div>
      <div className="msg-body">{message.body}</div>
      <div className="msg-time">{formatTime(message.createdAt)}</div>
    </article>
  )
}
