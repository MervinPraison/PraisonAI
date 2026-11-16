import { describe, expect, it } from '@jest/globals';
import { HooksManager } from '../../src/hooks/manager';

describe('HooksManager inspection', () => {
  it('allows registering and executing hooks after inspection', async () => {
    const manager = new HooksManager();
    const called: string[] = [];
    const first = manager.register('pre_tool_call', () => { called.push('first'); });
    const snapshot = manager.getHooks('pre_tool_call');
    const second = manager.register('pre_tool_call', () => { called.push('second'); }, { priority: 1 });
    expect(snapshot.map(hook => hook.id)).toEqual([first]);
    expect(manager.getHooks('pre_tool_call').map(hook => hook.id)).toEqual([second, first]);
    expect((await manager.execute('pre_tool_call', {})).success).toBe(true);
    expect(called).toEqual(['second', 'first']);
  });

  it('allows unregistering a hook after inspection', async () => {
    const manager = new HooksManager();
    const called: string[] = [];
    const first = manager.register('pre_tool_call', () => { called.push('first'); });
    const second = manager.register('pre_tool_call', () => { called.push('second'); });
    const snapshot = manager.getHooks('pre_tool_call');
    expect(manager.unregister(first)).toBe(true);
    expect(snapshot.map(hook => hook.id)).toEqual([first, second]);
    expect(manager.getStats().totalHooks).toBe(1);
    await manager.execute('pre_tool_call', {});
    expect(called).toEqual(['second']);
  });

  it('keeps returned arrays frozen against caller mutations', () => {
    const manager = new HooksManager();
    const id = manager.register('pre_tool_call', () => {});
    const snapshot = manager.getHooks('pre_tool_call');
    expect(Object.isFrozen(snapshot)).toBe(true);
    expect(() => (snapshot as unknown[]).pop()).toThrow(TypeError);
    expect(manager.getHooks('pre_tool_call').map(hook => hook.id)).toEqual([id]);
  });

  it('allows first registration after inspecting an empty event', () => {
    const manager = new HooksManager();
    const snapshot = manager.getHooks('pre_tool_call');
    const id = manager.register('pre_tool_call', () => {});
    expect(snapshot).toEqual([]);
    expect(Object.isFrozen(snapshot)).toBe(true);
    expect(manager.getHooks('pre_tool_call').map(hook => hook.id)).toEqual([id]);
  });
});
