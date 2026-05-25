import type { Message } from '../../shared/contracts'
import { formatTime } from '../lib/time'

interface Props {
  message: Message
}

export function MessageBubble({ message }: Props) {
  return (
    <article className={`message ${message.direction} ${message.deliveryState}`}>
      <div className="bubble">
        <div className="message-author">
          <span>{message.author}</span>
          <span className={`delivery-state ${message.deliveryState}`}>{message.deliveryState}</span>
        </div>
        <p>{message.body}</p>
        <footer>{formatTime(message.createdAt)}</footer>
      </div>
    </article>
  )
}
