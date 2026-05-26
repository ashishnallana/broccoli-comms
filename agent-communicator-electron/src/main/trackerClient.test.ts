import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { createServer } from 'node:net'
import { afterEach, describe, expect, it } from 'vitest'
import {
  localConversationKey,
  mergeConversationMessages,
  messageMatchesConversation,
  resolveSelfAgentName,
  resolveTrackerSocket,
  trackerAgentToSummary,
  trackerMessageTargetParams,
  trackerMessageToMessage,
  LocalTrackerClient,
} from './trackerClient'

function env(values: Record<string, string | undefined>): NodeJS.ProcessEnv {
  return values as NodeJS.ProcessEnv
}

const tempDirs: string[] = []

afterEach(async () => {
  await Promise.all(tempDirs.splice(0).map((dir) => rm(dir, { recursive: true, force: true })))
})

async function withFakeTracker<T>(
  handler: (method: string, params: Record<string, unknown>) => unknown,
  run: (socketPath: string) => Promise<T>,
): Promise<T> {
  const dir = await mkdtemp(join(tmpdir(), 'electron-tracker-test-'))
  tempDirs.push(dir)
  const socketPath = join(dir, 'agent-tracker.sock')
  const server = createServer((socket) => {
    const chunks: Buffer[] = []
    socket.on('data', (chunk) => chunks.push(Buffer.from(chunk)))
    socket.on('end', () => {
      try {
        const request = JSON.parse(Buffer.concat(chunks).toString('utf8')) as {
          id: number
          method: string
          params?: Record<string, unknown>
        }
        const result = handler(request.method, request.params || {})
        socket.end(JSON.stringify({ jsonrpc: '2.0', id: request.id, result }))
      } catch (error) {
        socket.end(
          JSON.stringify({
            jsonrpc: '2.0',
            id: 1,
            error: { code: -32000, message: error instanceof Error ? error.message : String(error) },
          }),
        )
      }
    })
  })
  await new Promise<void>((resolve, reject) => {
    server.once('error', reject)
    server.listen(socketPath, resolve)
  })
  try {
    return await run(socketPath)
  } finally {
    await new Promise<void>((resolve) => server.close(() => resolve()))
  }
}

describe('resolveTrackerSocket', () => {
  it('prefers explicit AGENT_TRACKER_SOCKET', () => {
    expect(
      resolveTrackerSocket(
        env({
          AGENT_TRACKER_SOCKET: '/tmp/private/tracker.sock',
          BROCCOLI_COMMS_RUNTIME_DIR: '/tmp/runtime',
        }),
      ),
    ).toBe('/tmp/private/tracker.sock')
  })

  it('uses BROCCOLI_COMMS_RUNTIME_DIR without falling back to cache or tmux env', () => {
    expect(
      resolveTrackerSocket(
        env({
          BROCCOLI_COMMS_RUNTIME_DIR: '/run/user/1000/broccoli-comms',
          TMUX: '/tmp/inherited-tmux,1,0',
          AGENT_TRACKER_TMUX_SOCKET: '/tmp/tmux.sock',
        }),
      ),
    ).toBe('/run/user/1000/broccoli-comms/agent-tracker.sock')
  })

  it('returns undefined when no explicit tracker runtime is provided', () => {
    expect(resolveTrackerSocket(env({ XDG_CACHE_HOME: '/tmp/cache', TMUX: '/tmp/tmux,1,0' }))).toBeUndefined()
  })
})

describe('resolveSelfAgentName', () => {
  it('prefers explicit Electron inbox identity env vars', () => {
    expect(
      resolveSelfAgentName(
        env({
          BROCCOLI_COMMS_ELECTRON_AGENT_NAME: 'desktop-user',
          AGENT_COMMUNICATOR_ELECTRON_AGENT_NAME: 'fallback-desktop',
          AGENT_NAME: 'pane-agent',
        }),
      ),
    ).toBe('desktop-user')
  })

  it('falls back through legacy Electron env, ignores launching pane AGENT_NAME, then uses agent-communicator', () => {
    expect(resolveSelfAgentName(env({ AGENT_COMMUNICATOR_ELECTRON_AGENT_NAME: 'desktop' }))).toBe('desktop')
    expect(resolveSelfAgentName(env({ AGENT_NAME: 'pane-agent' }))).toBe('agent-communicator')
    expect(resolveSelfAgentName(env({}))).toBe('agent-communicator')
  })
})

describe('tracker identity and target params', () => {
  it('uses stable local agent IDs for conversation keys', () => {
    expect(localConversationKey({ agent_id: 'agent-id-1', name: 'alpha' }, 'alpha')).toBe('local:agent-id-1')
    expect(localConversationKey({ uuid: 'uuid-1', name: 'alpha' }, 'alpha')).toBe('local:uuid-1')
    expect(localConversationKey({ name: 'alpha' }, 'alpha')).toBe('alpha')
  })

  it('maps local stable IDs to tracker agent_id send params', () => {
    expect(trackerMessageTargetParams({ scope: 'local', id: 'local:agent-id-1', address: 'alpha' })).toEqual({
      agent_id: 'agent-id-1',
    })
  })

  it('maps legacy local names, supports remote host-qualified targets, and handles registry targets at the main-process boundary', () => {
    expect(trackerMessageTargetParams({ scope: 'local', id: 'alpha', address: 'alpha' })).toEqual({ agent_name: 'alpha' })
    expect(trackerMessageTargetParams({ scope: 'remote', id: 'host/alpha', address: 'host/alpha' })).toEqual({ target_address: 'host/alpha' })
    expect(trackerMessageTargetParams({ scope: 'local', id: 'bad', address: 'host/alpha' })).toEqual({ target_address: 'host/alpha' })
    expect(trackerMessageTargetParams({ scope: 'local', id: 'bad', address: 'registry:host/alpha' })).toEqual({ target_address: 'registry:host/alpha' })
  })
})

describe('LocalTrackerClient tracker Simple View behavior', () => {
  it('lists both local and remote targets while excluding the configured Electron inbox identity', async () => {
    await withFakeTracker(
      (method, params) => {
        if (method === 'ensure_mailbox') {
          expect(params).toEqual({ agent_name: 'desktop' })
          return { name: 'desktop', agent_id: 'self-id', uuid: 'self-id' }
        }
        expect(method).toBe('list')
        expect(params).toEqual({ agent_name: 'desktop', include_remote: true })
        return {
          desktop: { agent_id: 'self-id', name: 'desktop', scope: 'local', cwd: '/repo/app' },
          alpha: { agent_id: 'alpha-id', name: 'alpha', scope: 'local', cwd: '/repo/alpha' },
          'host/beta': { agent_id: 'beta-id', name: 'host/beta', scope: 'remote', target_address: 'host/beta' },
        }
      },
      async (socketPath) => {
        const client = new LocalTrackerClient(socketPath, 'desktop')
        const agents = await client.listAgents()
        expect(agents.map((agent) => agent.name).sort()).toEqual(['alpha', 'host/beta'])
        expect(agents.find(a => a.name === 'alpha')).toMatchObject({ id: 'local:alpha-id', scope: 'local', canDirectControl: false })
        expect(agents.find(a => a.name === 'host/beta')).toMatchObject({ id: 'remote:host/beta', scope: 'remote', canDirectControl: false })
      },
    )
  })

  it('sends to the selected local agent as the configured inbox identity and reads matching replies', async () => {
    const calls: Array<{ method: string; params: Record<string, unknown> }> = []
    await withFakeTracker(
      (method, params) => {
        calls.push({ method, params })
        if (method === 'ensure_mailbox') return { name: 'desktop', agent_id: 'self-id', uuid: 'self-id' }
        if (method === 'list') {
          return {
            desktop: { agent_id: 'self-id', name: 'desktop', scope: 'local', cwd: '/repo/app' },
            alpha: { agent_id: 'alpha-id', name: 'alpha', scope: 'local', cwd: '/repo/alpha' },
            beta: { agent_id: 'beta-id', name: 'beta', scope: 'local', cwd: '/repo/beta' },
          }
        }
        if (method === 'send_message') return true
        if (method === 'get_inbox') {
          expect(params).toMatchObject({ agent_name: 'desktop', clear: false, last_n: 100, mark_read: false, sender_agent_id: 'alpha-id' })
          return {
            mode: 'last_n',
            messages: [
              {
                sender: 'alpha',
                sender_agent_id: 'alpha-id',
                timestamp: '2026-05-25T00:00:02.000Z',
                message: 'reply from alpha',
                message_id: 'reply-1',
              },
              {
                sender: 'beta',
                sender_agent_id: 'beta-id',
                timestamp: '2026-05-25T00:00:03.000Z',
                message: 'not this conversation',
                message_id: 'reply-2',
              },
            ],
          }
        }
        throw new Error(`unexpected method ${method}`)
      },
      async (socketPath) => {
        const client = new LocalTrackerClient(socketPath, 'desktop')
        const [alpha] = await client.listAgents()
        const send = await client.sendMessage({ scope: 'local', id: alpha.id, address: alpha.address }, 'hello alpha')
        expect(send.ok).toBe(true)
        expect(calls.find((call) => call.method === 'send_message')?.params).toMatchObject({
          agent_id: 'alpha-id',
          sender_name: 'desktop',
          message: 'hello alpha',
        })

        const messages = await client.listMessages(alpha.conversationKey)
        expect(messages.map((message) => message.body).sort()).toEqual(['hello alpha', 'reply from alpha'])
        expect(messages.find((message) => message.body === 'hello alpha')).toMatchObject({ direction: 'outbound' })
        expect(messages.find((message) => message.body === 'reply from alpha')).toMatchObject({ direction: 'inbound' })
      },
    )
  })

  it('falls back to standard register RPC when ensure_mailbox method is not found on older daemons', async () => {
    const calls: Array<{ method: string; params: Record<string, unknown> }> = []
    await withFakeTracker(
      (method, params) => {
        calls.push({ method, params })
        if (method === 'ensure_mailbox') {
          throw new Error('Method not found: ensure_mailbox')
        }
        if (method === 'register') {
          return { success: true }
        }
        if (method === 'list') {
          return {}
        }
        throw new Error(`unexpected method ${method}`)
      },
      async (socketPath) => {
        const client = new LocalTrackerClient(socketPath, 'desktop')
        const agents = await client.listAgents()
        expect(agents).toEqual([])

        expect(calls[0]).toMatchObject({ method: 'ensure_mailbox', params: { agent_name: 'desktop' } })
        expect(calls[1]).toMatchObject({
          method: 'register',
          params: {
            session: 'mailbox',
            name: 'desktop',
            agent_type: 'agent-communicator-ui',
            agent_id: '00000000-0000-5000-8000-000000000001',
          },
        })
      },
    )
  })

  it('captures a local pane snapshot and delivers it to the communicator inbox successfully', async () => {
    const calls: Array<{ method: string; params: Record<string, unknown> }> = []
    await withFakeTracker(
      (method, params) => {
        calls.push({ method, params })
        if (method === 'ensure_mailbox') return { name: 'desktop', agent_id: 'self-id', uuid: 'self-id' }
        if (method === 'list') {
          return {
            desktop: { agent_id: 'self-id', name: 'desktop', scope: 'local' },
            alpha: { agent_id: 'alpha-id', name: 'alpha', scope: 'local' },
          }
        }
        if (method === 'capture_pane') {
          expect(params).toMatchObject({ agent_id: 'alpha-id', last_lines: 25, include_ansi: false })
          return {
            agent_name: 'alpha',
            agent_id: 'alpha-id',
            tmux_pane: '%1',
            session: 'broccoli',
            copy_mode: false,
            captured_at: '2026-05-25T13:40:00.000Z',
            content: 'visible pane content',
          }
        }
        if (method === 'send_message') {
          expect(params).toMatchObject({
            agent_name: 'desktop',
            sender_name: 'alpha',
            sender_id: 'alpha-id',
          })
          expect(params.message).toContain('visible pane content')
          expect(params.message).toContain('### Pane Capture Snapshot from alpha')
          return true
        }
        throw new Error(`unexpected method ${method}`)
      },
      async (socketPath) => {
        const client = new LocalTrackerClient(socketPath, 'desktop')
        await client.listAgents()
        const result = await client.sendPaneCapture('local:alpha-id', 'desktop')
        expect(result.ok).toBe(true)
        expect(result.summary).toContain('Snapshot sent successfully')

        expect(calls.map((c) => c.method)).toEqual(['ensure_mailbox', 'list', 'capture_pane', 'send_message'])
      },
    )
  })

  it('dispatches a remote pane capture request successfully across tracker registries', async () => {
    const calls: Array<{ method: string; params: Record<string, unknown> }> = []
    await withFakeTracker(
      (method, params) => {
        calls.push({ method, params })
        if (method === 'ensure_mailbox') return { name: 'desktop', agent_id: 'self-id', uuid: 'self-id' }
        if (method === 'list') {
          return {
            desktop: { agent_id: 'self-id', name: 'desktop', scope: 'local' },
            'zephyrus/reviewer': { agent_id: 'rev-id', name: 'zephyrus/reviewer', scope: 'remote', target_address: 'zephyrus/reviewer', tracker_id: 'track-z' },
          }
        }
        if (method === 'publish_tracker_event') {
          const localHost = process.env.AGENT_TRACKER_HOSTNAME || require('node:os').hostname()
          expect(params).toMatchObject({
            target_tracker_id: 'track-z',
            event_type: 'pane_capture_request',
            payload: {
              source: 'reviewer',
              target: `${localHost}/desktop`,
              requester: 'desktop',
            },
          })
          return true
        }
        throw new Error(`unexpected method ${method}`)
      },
      async (socketPath) => {
        const client = new LocalTrackerClient(socketPath, 'desktop')
        await client.listAgents()
        const result = await client.sendPaneCapture('remote:zephyrus/reviewer', 'desktop')
        expect(result.ok).toBe(true)
        expect(result.summary).toContain('Remote pane capture request sent to zephyrus')

        expect(calls.map((c) => c.method)).toEqual(['ensure_mailbox', 'list', 'publish_tracker_event'])
      },
    )
  })

  it('injects local direct text and keys successfully', async () => {
    const calls: Array<{ method: string; params: Record<string, unknown> }> = []
    await withFakeTracker(
      (method, params) => {
        calls.push({ method, params })
        if (method === 'ensure_mailbox') return { name: 'desktop', agent_id: 'self-id', uuid: 'self-id' }
        if (method === 'list') {
          return {
            desktop: { agent_id: 'self-id', name: 'desktop', scope: 'local' },
            alpha: { agent_id: 'alpha-id', name: 'alpha', scope: 'local' },
          }
        }
        if (method === 'send_input') {
          return { success: true }
        }
        throw new Error(`unexpected method ${method}`)
      },
      async (socketPath) => {
        const client = new LocalTrackerClient(socketPath, 'desktop')
        await client.listAgents()

        const textResult = await client.sendDirectText({ scope: 'local', id: 'local:alpha-id', address: 'alpha' }, 'ls -la', true)
        expect(textResult.ok).toBe(true)
        expect(calls.find((c) => c.method === 'send_input' && c.params.input_type === 'text')?.params).toMatchObject({
          input_type: 'text',
          text: 'ls -la',
          submit: true,
          agent_id: 'alpha-id',
        })

        const keysResult = await client.sendDirectKeys({ scope: 'local', id: 'local:alpha-id', address: 'alpha' }, ['Escape', 'C-c'])
        expect(keysResult.ok).toBe(true)
        expect(calls.find((c) => c.method === 'send_input' && c.params.input_type === 'keys')?.params).toMatchObject({
          input_type: 'keys',
          keys: ['Escape', 'C-c'],
          agent_id: 'alpha-id',
        })
      },
    )
  })
})

describe('tracker Simple View mapping', () => {
  it('maps local tracker agents and disables direct control for this phase', () => {
    const summary = trackerAgentToSummary('alpha', { agent_id: 'id-1', status: 'working', cwd: '/repo/project' })
    expect(summary).toMatchObject({
      id: 'local:id-1',
      conversationKey: 'local:id-1',
      scope: 'local',
      status: 'busy',
      project: 'project',
      canDirectControl: false,
    })
  })

  it('maps remote tracker rows successfully', () => {
    expect(trackerAgentToSummary('host/alpha', { scope: 'remote', target_address: 'host/alpha', tracker_id: 'reg-a' })).toMatchObject({
      id: 'remote:host/alpha',
      scope: 'remote',
      project: 'reg-a',
      address: 'host/alpha'
    })
  })

  it('maps tracker inbox messages into one-to-one timeline messages', () => {
    expect(
      trackerMessageToMessage('local:id-1', {
        sender: 'alpha',
        timestamp: '2026-05-25T00:00:00.000Z',
        message: 'hello',
        message_id: 'm1',
      }),
    ).toMatchObject({
      id: 'm1',
      conversationKey: 'local:id-1',
      direction: 'inbound',
      author: 'alpha',
      body: 'hello',
      deliveryState: 'received',
    })
  })

  it('recognizes the configured Electron identity as outbound', () => {
    expect(
      trackerMessageToMessage(
        'local:id-1',
        { sender: 'desktop-user', timestamp: '2026-05-25T00:00:00.000Z', message: 'sent', message_id: 'm2' },
        'desktop-user',
      ),
    ).toMatchObject({ direction: 'outbound', author: 'you', deliveryState: 'delivered' })
  })

  it('filters self inbox messages to the selected local conversation by id or name', () => {
    expect(messageMatchesConversation({ sender_agent_id: 'id-1', sender: 'old-name' }, { agent_id: 'id-1', name: 'alpha' })).toBe(true)
    expect(messageMatchesConversation({ sender: 'alpha' }, { name: 'alpha' })).toBe(true)
    expect(messageMatchesConversation({ sender_agent_id: 'id-2', sender: 'beta' }, { agent_id: 'id-1', name: 'alpha' })).toBe(false)
  })

  it('merges received self-inbox messages with locally sent messages chronologically', () => {
    const merged = mergeConversationMessages(
      [
        {
          id: 'in-1',
          conversationKey: 'local:id-1',
          direction: 'inbound',
          author: 'alpha',
          body: 'reply',
          createdAt: '2026-05-25T00:00:02.000Z',
          deliveryState: 'received',
        },
      ],
      [
        {
          id: 'out-1',
          conversationKey: 'local:id-1',
          direction: 'outbound',
          author: 'you',
          body: 'hello',
          createdAt: '2026-05-25T00:00:01.000Z',
          deliveryState: 'delivered',
        },
      ],
    )
    expect(merged.map((message) => message.id)).toEqual(['out-1', 'in-1'])
  })
})
