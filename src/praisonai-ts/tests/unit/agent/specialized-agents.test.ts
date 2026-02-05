/**
 * Specialized Agents Tests - TDD for Vision, Video, Embedding, Realtime agents
 * Python parity tests
 */

import { describe, it, expect } from '@jest/globals';
import {
  VisionAgent,
  VisionConfig,
  createVisionAgent,
  VideoAgent,
  VideoConfig,
  createVideoAgent,
  EmbeddingAgent,
  EmbeddingConfig,
  createEmbeddingAgent,
  RealtimeAgent,
  RealtimeConfig,
  createRealtimeAgent,
} from '../../../src/agent';

describe('VisionAgent (Python Parity)', () => {
  describe('Construction', () => {
    it('should create with minimal config', () => {
      const agent = new VisionAgent({});
      expect(agent.name).toBe('VisionAgent');
    });

    it('should have DEFAULT_MODEL constant', () => {
      expect(VisionAgent.DEFAULT_MODEL).toBe('gpt-4o');
    });

    it('should accept full config', () => {
      const agent = new VisionAgent({
        name: 'MyVision',
        llm: 'gpt-4o',
        vision: { detail: 'high' },
        verbose: false,
      });
      expect(agent.name).toBe('MyVision');
    });
  });

  describe('Methods', () => {
    it('should have analyze method', () => {
      const agent = new VisionAgent({});
      expect(typeof agent.analyze).toBe('function');
    });

    it('should have ask method', () => {
      const agent = new VisionAgent({});
      expect(typeof agent.ask).toBe('function');
    });

    it('should have describe method', () => {
      const agent = new VisionAgent({});
      expect(typeof agent.describe).toBe('function');
    });

    it('should have detectObjects method', () => {
      const agent = new VisionAgent({});
      expect(typeof agent.detectObjects).toBe('function');
    });

    it('should have extractText method', () => {
      const agent = new VisionAgent({});
      expect(typeof agent.extractText).toBe('function');
    });
  });

  describe('Factory', () => {
    it('should create VisionAgent via factory', () => {
      const agent = createVisionAgent({ name: 'FactoryVision' });
      expect(agent).toBeInstanceOf(VisionAgent);
      expect(agent.name).toBe('FactoryVision');
    });
  });
});

describe('VideoAgent (Python Parity)', () => {
  describe('Construction', () => {
    it('should create with minimal config', () => {
      const agent = new VideoAgent({});
      expect(agent.name).toBe('VideoAgent');
    });

    it('should have DEFAULT_MODEL constant', () => {
      expect(VideoAgent.DEFAULT_MODEL).toBe('gpt-4o');
    });

    it('should accept full config', () => {
      const agent = new VideoAgent({
        name: 'MyVideo',
        video: { maxDuration: 600, transcribeAudio: true },
      });
      expect(agent.name).toBe('MyVideo');
    });
  });

  describe('Methods', () => {
    it('should have analyze method', () => {
      const agent = new VideoAgent({});
      expect(typeof agent.analyze).toBe('function');
    });

    it('should have ask method', () => {
      const agent = new VideoAgent({});
      expect(typeof agent.ask).toBe('function');
    });

    it('should have describe method', () => {
      const agent = new VideoAgent({});
      expect(typeof agent.describe).toBe('function');
    });

    it('should have summarize method', () => {
      const agent = new VideoAgent({});
      expect(typeof agent.summarize).toBe('function');
    });

    it('should have extractKeyMoments method', () => {
      const agent = new VideoAgent({});
      expect(typeof agent.extractKeyMoments).toBe('function');
    });
  });

  describe('Factory', () => {
    it('should create VideoAgent via factory', () => {
      const agent = createVideoAgent({ name: 'FactoryVideo' });
      expect(agent).toBeInstanceOf(VideoAgent);
    });
  });
});

describe('EmbeddingAgent (Python Parity)', () => {
  describe('Construction', () => {
    it('should create with minimal config', () => {
      const agent = new EmbeddingAgent({});
      expect(agent.name).toBe('EmbeddingAgent');
    });

    it('should have DEFAULT_MODEL constant', () => {
      expect(EmbeddingAgent.DEFAULT_MODEL).toBe('text-embedding-3-small');
    });

    it('should accept model alias', () => {
      const agent = new EmbeddingAgent({
        model: 'text-embedding-3-large',
      });
      expect(agent.name).toBe('EmbeddingAgent');
    });
  });

  describe('Methods', () => {
    it('should have embed method', () => {
      const agent = new EmbeddingAgent({});
      expect(typeof agent.embed).toBe('function');
    });

    it('should have embedMany method', () => {
      const agent = new EmbeddingAgent({});
      expect(typeof agent.embedMany).toBe('function');
    });

    it('should have cosineSimilarity method', () => {
      const agent = new EmbeddingAgent({});
      expect(typeof agent.cosineSimilarity).toBe('function');
    });

    it('should have findMostSimilar method', () => {
      const agent = new EmbeddingAgent({});
      expect(typeof agent.findMostSimilar).toBe('function');
    });

    it('should calculate cosine similarity correctly', () => {
      const agent = new EmbeddingAgent({});
      const a = [1, 0, 0];
      const b = [1, 0, 0];
      expect(agent.cosineSimilarity(a, b)).toBeCloseTo(1.0);

      const c = [1, 0, 0];
      const d = [0, 1, 0];
      expect(agent.cosineSimilarity(c, d)).toBeCloseTo(0.0);
    });
  });

  describe('Factory', () => {
    it('should create EmbeddingAgent via factory', () => {
      const agent = createEmbeddingAgent({});
      expect(agent).toBeInstanceOf(EmbeddingAgent);
    });
  });
});

describe('RealtimeAgent (Python Parity)', () => {
  describe('Construction', () => {
    it('should create with minimal config', () => {
      const agent = new RealtimeAgent({});
      expect(agent.name).toBe('RealtimeAgent');
    });

    it('should have DEFAULT_MODEL constant', () => {
      expect(RealtimeAgent.DEFAULT_MODEL).toBe('gpt-4o-realtime-preview');
    });

    it('should accept full config', () => {
      const agent = new RealtimeAgent({
        name: 'MyRealtime',
        realtime: { voice: 'nova', vadEnabled: true },
        instructions: 'Be helpful',
      });
      expect(agent.name).toBe('MyRealtime');
    });
  });

  describe('Connection Methods', () => {
    it('should have connect method', () => {
      const agent = new RealtimeAgent({});
      expect(typeof agent.connect).toBe('function');
    });

    it('should have disconnect method', () => {
      const agent = new RealtimeAgent({});
      expect(typeof agent.disconnect).toBe('function');
    });

    it('should have isConnected method', () => {
      const agent = new RealtimeAgent({});
      expect(typeof agent.isConnected).toBe('function');
      expect(agent.isConnected()).toBe(false);
    });
  });

  describe('Audio Methods', () => {
    it('should have sendAudio method', () => {
      const agent = new RealtimeAgent({});
      expect(typeof agent.sendAudio).toBe('function');
    });

    it('should have commitAudio method', () => {
      const agent = new RealtimeAgent({});
      expect(typeof agent.commitAudio).toBe('function');
    });

    it('should have clearAudio method', () => {
      const agent = new RealtimeAgent({});
      expect(typeof agent.clearAudio).toBe('function');
    });
  });

  describe('Event Handling', () => {
    it('should have on method', () => {
      const agent = new RealtimeAgent({});
      expect(typeof agent.on).toBe('function');
    });

    it('should have off method', () => {
      const agent = new RealtimeAgent({});
      expect(typeof agent.off).toBe('function');
    });

    it('should emit events on connect', async () => {
      const agent = new RealtimeAgent({});
      let eventReceived = false;
      
      agent.on('session.created', () => {
        eventReceived = true;
      });
      
      await agent.connect();
      expect(eventReceived).toBe(true);
    });
  });

  describe('Configuration', () => {
    it('should have getConfig method', () => {
      const agent = new RealtimeAgent({});
      expect(typeof agent.getConfig).toBe('function');
      
      const config = agent.getConfig();
      expect(config.voice).toBe('alloy');
      expect(config.vadEnabled).toBe(true);
    });

    it('should have updateConfig method', () => {
      const agent = new RealtimeAgent({});
      expect(typeof agent.updateConfig).toBe('function');
    });
  });

  describe('Factory', () => {
    it('should create RealtimeAgent via factory', () => {
      const agent = createRealtimeAgent({ name: 'FactoryRealtime' });
      expect(agent).toBeInstanceOf(RealtimeAgent);
    });
  });
});
