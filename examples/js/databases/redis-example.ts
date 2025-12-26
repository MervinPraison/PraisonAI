/**
 * Redis Database Example
 */

import { createMemoryRedis } from '../../../src/praisonai-ts/src';

async function main() {
  // Use in-memory Redis for this example
  const redis = createMemoryRedis();
  await redis.connect();

  console.log('Connected to Redis');

  // Basic get/set
  await redis.set('user:123', { name: 'John', role: 'admin' });
  const user = await redis.get('user:123');
  console.log('User:', user);

  // Set with TTL
  await redis.set('session:abc', { token: 'xyz' }, 60);
  const ttl = await redis.ttl('session:abc');
  console.log('Session TTL:', ttl, 'seconds');

  // Hash operations
  await redis.hset('profile:123', 'email', 'john@example.com');
  await redis.hset('profile:123', 'phone', '555-1234');
  const profile = await redis.hgetall('profile:123');
  console.log('Profile:', profile);

  // List operations
  await redis.rpush('queue:tasks', { id: 1, type: 'process' });
  await redis.rpush('queue:tasks', { id: 2, type: 'notify' });
  const tasks = await redis.lrange('queue:tasks', 0, -1);
  console.log('Tasks:', tasks);

  // Pub/Sub (memory only)
  await redis.subscribe('events', (message) => {
    console.log('Received event:', message);
  });
  await redis.publish('events', JSON.stringify({ type: 'user_joined' }));

  // Cleanup
  await redis.disconnect();
  console.log('Done!');
}

main().catch(console.error);
