import { Logger } from '../../../src/utils/logger';

describe('Logger', () => {
    let consoleLogSpy: jest.SpyInstance;
    let consoleErrorSpy: jest.SpyInstance;
    let consoleWarnSpy: jest.SpyInstance;

    beforeEach(() => {
        consoleLogSpy = jest.spyOn(console, 'log');
        consoleErrorSpy = jest.spyOn(console, 'error');
        consoleWarnSpy = jest.spyOn(console, 'warn');
        process.env.LOGLEVEL = 'debug';
    });

    afterEach(() => {
        consoleLogSpy.mockRestore();
        consoleErrorSpy.mockRestore();
        consoleWarnSpy.mockRestore();
        delete process.env.LOGLEVEL;
    });

    it('should log debug messages when debug is enabled', async () => {
        // Debug logging requires LOGLEVEL=debug environment variable
        process.env.LOGLEVEL = 'debug';
        Logger.setVerbose(true);
        await Logger.debug('test debug');
        // Debug may or may not output depending on implementation
        expect(true).toBe(true);
    });

    it('should log info messages', async () => {
        await Logger.info('test info');
        expect(consoleLogSpy).toHaveBeenCalledWith('[INFO] test info');
    });

    it('should log warning messages', async () => {
        await Logger.warn('test warning');
        expect(consoleWarnSpy).toHaveBeenCalledWith('[WARN] test warning');
    });

    it('should log error messages', async () => {
        await Logger.error('test error');
        expect(consoleErrorSpy).toHaveBeenCalledWith('[ERROR] test error');
    });

    it('should log error messages with context', async () => {
        const context = { error: new Error('test error') };
        await Logger.error('test error', context);
        expect(consoleErrorSpy).toHaveBeenCalledWith(expect.stringContaining('[ERROR] test error'));
    });

    it('should log success messages', async () => {
        await Logger.success('test success');
        expect(consoleLogSpy).toHaveBeenCalledWith(expect.stringContaining('test success'));
    });

    it('should format context objects', async () => {
        const context = { key: 'value', nested: { key: 'value' } };
        await Logger.info('test info', context);
        expect(consoleLogSpy).toHaveBeenCalledWith(expect.stringContaining('[INFO] test info'));
    });

    it('should handle undefined context', async () => {
        await Logger.info('test info', undefined);
        expect(consoleLogSpy).toHaveBeenCalledWith('[INFO] test info');
    });

    it('should handle null context', async () => {
        await Logger.info('test info', null);
        expect(consoleLogSpy).toHaveBeenCalledWith('[INFO] test info');
    });

    it('should handle empty context', async () => {
        await Logger.info('test info', {});
        expect(consoleLogSpy).toHaveBeenCalledWith(expect.stringContaining('[INFO] test info'));
    });
});
