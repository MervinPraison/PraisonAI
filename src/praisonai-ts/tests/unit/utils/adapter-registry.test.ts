import {
  AdapterRegistry,
  AdapterCreationError,
  BackendNotAvailableError,
  isBackendUnavailableError,
} from '../../../src/utils/adapter-registry';

interface Thing {
  kind: string;
  kwargs: Record<string, unknown>;
}

class ThingAdapter implements Thing {
  kind = 'class';
  constructor(public kwargs: Record<string, unknown>) {}
}

describe('AdapterRegistry', () => {
  let registry: AdapterRegistry<Thing>;

  beforeEach(() => {
    registry = new AdapterRegistry<Thing>('Thing');
  });

  it('instantiates a registered class with the kwargs', () => {
    registry.registerAdapter('a', ThingAdapter);
    const inst = registry.getAdapter('a', { x: 1 });
    expect(inst).toBeInstanceOf(ThingAdapter);
    expect(inst?.kwargs).toEqual({ x: 1 });
    expect(registry.getAdapter('a')?.kwargs).toEqual({});
  });

  it('calls a registered factory with the kwargs', () => {
    const factory = jest.fn((kwargs: Record<string, unknown>) => ({ kind: 'factory', kwargs }));
    registry.registerFactory('f', factory);
    expect(registry.getAdapter('f', { y: 2 })).toEqual({ kind: 'factory', kwargs: { y: 2 } });
    expect(factory).toHaveBeenCalledWith({ y: 2 });
  });

  it('prefers the factory when both a class and a factory share a name', () => {
    registry.registerAdapter('both', ThingAdapter);
    registry.registerFactory('both', (kwargs) => ({ kind: 'factory', kwargs }));
    expect(registry.getAdapter('both')?.kind).toBe('factory');
  });

  it('returns null for unknown names', () => {
    expect(registry.getAdapter('missing')).toBeNull();
  });

  it('returns null when the backend is unavailable (ImportError analogue)', () => {
    registry.registerFactory('f', () => {
      throw new BackendNotAvailableError('f', 'not installed');
    });
    class Missing {
      constructor(_kwargs: Record<string, unknown>) {
        const err = new Error('Cannot find module') as Error & { code: string };
        err.code = 'MODULE_NOT_FOUND';
        throw err;
      }
    }
    registry.registerAdapter('c', Missing as unknown as new (k: Record<string, unknown>) => Thing);
    expect(registry.getAdapter('f')).toBeNull();
    expect(registry.getAdapter('c')).toBeNull();
  });

  it('wraps any other construction failure in AdapterCreationError with the cause', () => {
    const boom = new TypeError('bad config');
    registry.registerFactory('f', () => {
      throw boom;
    });
    expect(() => registry.getAdapter('f')).toThrow(AdapterCreationError);
    try {
      registry.getAdapter('f');
    } catch (err) {
      expect((err as AdapterCreationError).cause).toBe(boom);
      expect((err as Error).message).toBe(
        "Failed to create Thing adapter 'f' via factory. Check adapter config and installed extras.",
      );
    }

    class Bad {
      constructor(_kwargs: Record<string, unknown>) {
        throw new RangeError('nope');
      }
    }
    registry.registerAdapter('c', Bad as unknown as new (k: Record<string, unknown>) => Thing);
    expect(() => registry.getAdapter('c')).toThrow(
      "Failed to instantiate Thing adapter 'c'. Check adapter constructor args and installed extras.",
    );
  });

  it('lists names sorted and de-duplicated, and reports availability', () => {
    registry.registerFactory('zeta', (kwargs) => ({ kind: 'f', kwargs }));
    registry.registerAdapter('alpha', ThingAdapter);
    registry.registerAdapter('zeta', ThingAdapter);
    expect(registry.listAdapters()).toEqual(['alpha', 'zeta']);
    expect(registry.isAvailable('alpha')).toBe(true);
    expect(registry.isAvailable('zeta')).toBe(true);
    expect(registry.isAvailable('omega')).toBe(false);
  });

  it('getFirstAvailable returns the first instantiable preference, skipping unavailable ones', () => {
    registry.registerFactory('unavailable', () => {
      throw new BackendNotAvailableError('unavailable', 'nope');
    });
    registry.registerAdapter('ok', ThingAdapter);
    const hit = registry.getFirstAvailable(['missing', 'unavailable', 'ok', 'later'], { z: 3 });
    expect(hit?.[0]).toBe('ok');
    expect(hit?.[1].kwargs).toEqual({ z: 3 });
    expect(registry.getFirstAvailable(['missing', 'unavailable'])).toBeNull();
    expect(registry.getFirstAvailable([])).toBeNull();
  });

  it('isBackendUnavailableError recognises the module-not-found family and nothing else', () => {
    expect(isBackendUnavailableError(new BackendNotAvailableError('x', 'm'))).toBe(true);
    expect(isBackendUnavailableError(Object.assign(new Error(), { code: 'ERR_MODULE_NOT_FOUND' }))).toBe(true);
    expect(isBackendUnavailableError(new Error('plain'))).toBe(false);
    expect(isBackendUnavailableError(null)).toBe(false);
    const err = new BackendNotAvailableError('x', 'm', 'npm i x');
    expect(err.backend).toBe('x');
    expect(err.installHint).toBe('npm i x');
    expect(err.name).toBe('BackendNotAvailableError');
    expect(err).toBeInstanceOf(Error);
  });
});
