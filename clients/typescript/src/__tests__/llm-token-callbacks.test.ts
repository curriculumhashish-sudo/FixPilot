/**
 * 测试 LLM token 流式传输回调
 *
 * 这些测试验证 LLM 模块中的 token 回调功能。
 */

import { TokenCallbackType, TokenStreamEvent } from '../llm/base';

describe('Token Callback Types', () => {
  describe('TokenStreamEvent', () => {
    it('should have correct structure for streaming token', () => {
      const event: TokenStreamEvent = {
        token: 'Hello',
        isFinal: false,
        accumulated: 'Hello',
        index: 0,
      };

      expect(event.token).toBe('Hello');
      expect(event.isFinal).toBe(false);
      expect(event.accumulated).toBe('Hello');
      expect(event.index).toBe(0);
    });

    it('should have correct structure for final token', () => {
      const event: TokenStreamEvent = {
        token: '',
        isFinal: true,
        accumulated: 'Full response text',
        index: 20,
        model: 'gpt-4',
      };

      expect(event.isFinal).toBe(true);
      expect(event.accumulated).toBe('Full response text');
      expect(event.model).toBe('gpt-4');
    });
  });

  describe('TokenCallbackType', () => {
    it('should accept a function that receives TokenStreamEvent', () => {
      const events: TokenStreamEvent[] = [];
      const callback: TokenCallbackType = (event: TokenStreamEvent) => {
        events.push(event);
      };

      callback({
        token: 'Hello',
        isFinal: false,
        accumulated: 'Hello',
        index: 0,
      });

      callback({
        token: ' World',
        isFinal: false,
        accumulated: 'Hello World',
        index: 1,
      });

      callback({
        token: '',
        isFinal: true,
        accumulated: 'Hello World',
        index: 2,
      });

      expect(events).toHaveLength(3);
      expect(events[0].token).toBe('Hello');
      expect(events[1].accumulated).toBe('Hello World');
      expect(events[2].isFinal).toBe(true);
    });
  });

  describe('Streaming Integration', () => {
    it('should support async callback functions', async () => {
      const events: TokenStreamEvent[] = [];
      // 注意：TokenCallbackType 是同步，但我们可以测试异步行为
      const asyncHandler = async (event: TokenStreamEvent) => {
        await new Promise((resolve) => setTimeout(resolve, 1));
        events.push(event);
      };

      await asyncHandler({
        token: 'Async',
        isFinal: false,
        accumulated: 'Async',
        index: 0,
      });

      expect(events).toHaveLength(1);
    });

    it('should track token indices correctly', () => {
      const indices: number[] = [];
      const callback: TokenCallbackType = (event: TokenStreamEvent) => {
        if (event.index !== undefined) {
          indices.push(event.index);
        }
      };

      // Simulate a 流式传输 response
      callback({ token: 'The', isFinal: false, accumulated: 'The', index: 0 });
      callback({ token: ' quick', isFinal: false, accumulated: 'The quick', index: 1 });
      callback({ token: ' brown', isFinal: false, accumulated: 'The quick brown', index: 2 });
      callback({ token: ' fox', isFinal: false, accumulated: 'The quick brown fox', index: 3 });
      callback({ token: '', isFinal: true, accumulated: 'The quick brown fox', index: 4 });

      expect(indices).toEqual([0, 1, 2, 3, 4]);
    });

    it('should accumulate content correctly', () => {
      const accumulated: string[] = [];
      const callback: TokenCallbackType = (event: TokenStreamEvent) => {
        if (event.accumulated) {
          accumulated.push(event.accumulated);
        }
      };

      callback({ token: 'Hello', isFinal: false, accumulated: 'Hello', index: 0 });
      callback({ token: ' ', isFinal: false, accumulated: 'Hello ', index: 1 });
      callback({ token: 'World', isFinal: false, accumulated: 'Hello World', index: 2 });
      callback({ token: '', isFinal: true, accumulated: 'Hello World', index: 3 });

      expect(accumulated).toEqual(['Hello', 'Hello ', 'Hello World', 'Hello World']);
    });
  });
});

describe('LLM Interface with Callbacks', () => {
  // 模拟对象 LLM 用于测试接口合规性
  class MockLLM {
    defaultModel = 'mock-model';
    private tokenCallback?: TokenCallbackType;

    setTokenCallback(callback: TokenCallbackType): void {
      this.tokenCallback = callback;
    }

    async simulateStreaming(text: string): Promise<void> {
      if (!this.tokenCallback) return;

      const words = text.split(' ');
      let accumulated = '';

      for (let i = 0; i < words.length; i++) {
        accumulated += (i > 0 ? ' ' : '') + words[i];
        this.tokenCallback({
          token: (i > 0 ? ' ' : '') + words[i],
          isFinal: false,
          accumulated,
          index: i,
        });
      }

      this.tokenCallback({
        token: '',
        isFinal: true,
        accumulated,
        index: words.length,
      });
    }
  }

  it('should integrate with mock LLM', async () => {
    const mockLLM = new MockLLM();
    const events: TokenStreamEvent[] = [];

    mockLLM.setTokenCallback((event) => {
      events.push(event);
    });

    await mockLLM.simulateStreaming('Hello World Test');

    expect(events.length).toBe(4); // 3 个内容活动 + 1 个最终活动
    expect(events[0].token).toBe('Hello');
    expect(events[1].token).toBe(' World');
    expect(events[2].token).toBe(' Test');
    expect(events[3].isFinal).toBe(true);
    expect(events[3].accumulated).toBe('Hello World Test');
  });
});
