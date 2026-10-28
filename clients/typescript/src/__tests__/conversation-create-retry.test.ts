import { createServer, Server } from 'node:http';
import { AddressInfo } from 'node:net';
import { ConversationClient } from '../client/conversation-client';
import { HttpError } from '../client/http-client';

/**
 * 当创建失败时，客户端会从 `fetch` 重新抛出传输层错误
 * 没有 HTTP 响应。 它的确切消息是特定于运行时的，因此仅
 * 断言稳定合约：一个简单的错误，绝不是 HttpError。
 */
async function expectPreservedTransportError(promise: Promise<unknown>) {
  const error = await promise.then(
    () => {
      throw new Error('expected createConversation to reject');
    },
    (rejection: unknown) => rejection
  );
  expect(error).toBeInstanceOf(Error);
  expect(error).not.toBeInstanceOf(HttpError);
}

interface ServerOptions {
  /** 宣传幂等创建功能。*/
  supportsRetry?: boolean;
  /** 提交后删除第一个 POST 上的连接。*/
  commitThenDrop?: boolean;
  /** 拒绝带有 HTTP 错误的 POST，而不是丢弃它。*/
  rejectPost?: boolean;
}

/**
 * 最小 Agent Server：为能力探测提供 `/server_info` 服务，并且
 * `/api/conversations` 用于创建。 每个场景控制是否丢弃
 * POST 已经提交到服务器端，重试就存在这种情况
 * 对于这种情况，a 重试不得变成重复项。
 */
function startServer(options: ServerOptions = {}) {
  const { supportsRetry = true, commitThenDrop = true, rejectPost = false } = options;
  const state = { creates: 0, committed: false, duplicates: 0 };

  const server = createServer((req, res) => {
    if (req.url?.startsWith('/server_info')) {
      res.writeHead(200, { 'content-type': 'application/json' });
      res.end(
        JSON.stringify({
          version: '1.47.0',
          capabilities: supportsRetry ? ['idempotent_conversation_create_v1'] : [],
        })
      );
      return;
    }

    state.creates++;
    req.resume();
    req.on('end', () => {
      if (rejectPost) {
        res.writeHead(400, { 'content-type': 'application/json' });
        res.end(JSON.stringify({ detail: 'invalid settings' }));
        return;
      }
      // 服务器上的重复创建会返回相同的对话； 不这样做的人会在这里开始第二次对话。
      //
      if (state.committed && !supportsRetry) {
        state.duplicates++;
      }
      state.committed = true;
      // 只有第一个POST失去响应； 重新发送必须是可应答的。
      if (commitThenDrop && state.creates === 1) {
        req.socket.destroy();
      } else {
        res.writeHead(200, { 'content-type': 'application/json' });
        res.end(JSON.stringify({ id: 'test-cid' }));
      }
    });
  });

  return { server, state };
}

async function listen(server: Server): Promise<string> {
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
  return `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
}

async function close(server: Server): Promise<void> {
  server.closeAllConnections();
  await new Promise<void>((resolve) => server.close(() => resolve()));
}

describe('conversation create response loss', () => {
  it('retries on a server that deduplicates concurrent creates', async () => {
    const { server, state } = startServer({ supportsRetry: true, commitThenDrop: true });
    const host = await listen(server);
    try {
      const result = await new ConversationClient({ host }).createConversation({
        conversation_id: 'test-cid',
        initial_message: { content: 'run once' },
      });
      expect(result.id).toBe('test-cid');
      // 提交的创建加上重新发送，服务器已对其进行重复数据删除。
      expect(state.creates).toBe(2);
      expect(state.duplicates).toBe(0);
    } finally {
      await close(server);
    }
  });

  it('does not replay the create against a server without the capability', async () => {
    const { server, state } = startServer({ supportsRetry: false, commitThenDrop: true });
    const host = await listen(server);
    try {
      await expectPreservedTransportError(
        new ConversationClient({ host }).createConversation({
          conversation_id: 'test-cid',
          initial_message: { content: 'run once' },
        })
      );
      // 此处重播将创建第二个对话并重新运行初始消息，因此必须显示传输层错误。
      //
      expect(state.creates).toBe(1);
    } finally {
      await close(server);
    }
  });

  it('does not retry when the caller supplied no conversation id', async () => {
    const { server, state } = startServer({ supportsRetry: true, commitThenDrop: true });
    const host = await listen(server);
    try {
      await expectPreservedTransportError(new ConversationClient({ host }).createConversation({}));
      expect(state.creates).toBe(1);
    } finally {
      await close(server);
    }
  });

  it('does not conceal server validation failures', async () => {
    const { server, state } = startServer({ supportsRetry: true, rejectPost: true });
    const host = await listen(server);
    try {
      await expect(
        new ConversationClient({ host }).createConversation({
          conversation_id: 'test-cid',
        })
      ).rejects.toMatchObject({ status: 400 });
      expect(state.creates).toBe(1);
    } finally {
      await close(server);
    }
  });
});
