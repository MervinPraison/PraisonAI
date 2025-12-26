/**
 * Voice Integrations
 * Provides adapters for TTS and STT services
 */

export * from './base';

// Re-export factory functions
export { createOpenAIVoice, createElevenLabsVoice } from './base';
