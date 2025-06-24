// Import types only
import type { Ora } from 'ora';
import type { Options as BoxenOptions } from 'boxen';
import type { TableConstructorOptions } from 'cli-table3';

// We'll load these dynamically since they're ES modules
let chalk: any;
let boxen: any;
let ora: any;
let Table: any;
let figlet: any;

// Load dependencies dynamically
async function loadDependencies() {
    try {
        const imports = await Promise.all([
            import('chalk'),
            import('boxen'),
            import('ora'),
            import('cli-table3'),
            import('figlet')
        ]);
        
        [chalk, boxen, ora, Table, figlet] = imports.map(imp => imp.default);
        return true;
    } catch (error) {
        console.warn('Pretty logging dependencies not available, falling back to basic logging');
        return false;
    }
}

export class PrettyLogger {
    private static spinner: Ora | null = null;
    private static lastSpinnerText: string = '';
    private static initialized: boolean = false;
    private static isLoaded: boolean = false;

    private static async init() {
        if (!this.initialized) {
            this.isLoaded = await loadDependencies();
            this.initialized = true;
        }
        return this.isLoaded;
    }

    static async showTitle(text: string): Promise<void> {
        if (!await this.init()) {
            console.log(text);
            return;
        }

        return new Promise((resolve, reject) => {
            figlet(text, (err: Error | null, data: string | undefined) => {
                if (err) {
                    reject(err);
                    return;
                }
                if (data) {
                    console.log(chalk.cyan(data));
                }
                resolve();
            });
        });
    }

    static async info(message: string, data?: unknown): Promise<void> {
        if (!await this.init()) {
            console.log(`ℹ ${message}`);
            if (data) console.log(data);
            return;
        }

        console.log(chalk.blue('ℹ'), chalk.blue(message));
        if (data) {
            console.log(boxen(JSON.stringify(data, null, 2), {
                padding: 1,
                margin: 1,
                borderStyle: 'round',
                borderColor: 'blue'
            } as BoxenOptions));
        }
    }

    static async success(message: string, data?: unknown): Promise<void> {
        if (!await this.init()) {
            console.log(`✓ ${message}`);
            if (data) console.log(data);
            return;
        }

        console.log(chalk.green('✓'), chalk.green(message));
        if (data) {
            console.log(boxen(JSON.stringify(data, null, 2), {
                padding: 1,
                margin: 1,
                borderStyle: 'round',
                borderColor: 'green'
            } as BoxenOptions));
        }
    }

    static async error(message: string, error?: unknown): Promise<void> {
        if (!await this.init()) {
            console.error(`✗ ${message}`);
            if (error) console.error(error);
            return;
        }

        console.log(chalk.red('✗'), chalk.red(message));
        if (error) {
            console.log(boxen(JSON.stringify(error, null, 2), {
                padding: 1,
                margin: 1,
                borderStyle: 'round',
                borderColor: 'red'
            } as BoxenOptions));
        }
    }

    static async warning(message: string, data?: unknown): Promise<void> {
        if (!await this.init()) {
            console.warn(`⚠ ${message}`);
            if (data) console.warn(data);
            return;
        }

        console.log(chalk.yellow('⚠'), chalk.yellow(message));
        if (data) {
            console.log(boxen(JSON.stringify(data, null, 2), {
                padding: 1,
                margin: 1,
                borderStyle: 'round',
                borderColor: 'yellow'
            } as BoxenOptions));
        }
    }

    static async startSpinner(text: string): Promise<void> {
        if (!await this.init()) {
            console.log(`⟳ ${text}`);
            return;
        }

        this.lastSpinnerText = text;
        this.spinner = ora({
            text: chalk.cyan(text),
            color: 'cyan'
        }).start();
    }

    static async updateSpinner(text: string): Promise<void> {
        if (!await this.init()) {
            console.log(`⟳ ${text}`);
            return;
        }

        if (this.spinner) {
            this.lastSpinnerText = text;
            this.spinner.text = chalk.cyan(text);
        }
    }

    static async stopSpinner(success: boolean = true): Promise<void> {
        if (!await this.init()) return;

        if (this.spinner) {
            if (success) {
                this.spinner.succeed(chalk.green(this.lastSpinnerText));
            } else {
                this.spinner.fail(chalk.red(this.lastSpinnerText));
            }
            this.spinner = null;
        }
    }

    static async table(headers: string[], data: (string | number)[][]): Promise<void> {
        if (!await this.init()) {
            console.log(headers.join('\t'));
            data.forEach(row => console.log(row.join('\t')));
            return;
        }

        const table = new Table({
            head: headers.map(h => chalk.cyan(h)),
            style: {
                head: [],
                border: []
            }
        } as TableConstructorOptions);

        data.forEach(row => table.push(row));
        console.log(table.toString());
    }

    static async section(title: string, content: string): Promise<void> {
        if (!await this.init()) {
            console.log(`\n=== ${title} ===`);
            console.log(content);
            console.log('='.repeat(title.length + 8));
            return;
        }

        console.log('\n' + boxen(chalk.bold(title) + '\n\n' + content, {
            padding: 1,
            margin: 1,
            borderStyle: 'double',
            borderColor: 'cyan'
        } as BoxenOptions));
    }
}
