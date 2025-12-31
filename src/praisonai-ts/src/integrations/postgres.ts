/**
 * Natural Language Postgres
 * 
 * Provides NL->SQL capabilities for querying PostgreSQL databases.
 */

export interface PostgresConfig {
  /** Database connection URL */
  connectionUrl: string;
  /** Schema to use (default: public) */
  schema?: string;
  /** Read-only mode (default: true for safety) */
  readOnly?: boolean;
  /** Allowed tables (whitelist) */
  allowedTables?: string[];
  /** Blocked tables (blacklist) */
  blockedTables?: string[];
  /** Maximum rows to return (default: 100) */
  maxRows?: number;
  /** Query timeout in ms (default: 30000) */
  timeout?: number;
}

export interface TableSchema {
  name: string;
  columns: ColumnSchema[];
  primaryKey?: string[];
  foreignKeys?: ForeignKey[];
}

export interface ColumnSchema {
  name: string;
  type: string;
  nullable: boolean;
  defaultValue?: string;
  description?: string;
}

export interface ForeignKey {
  columns: string[];
  referencedTable: string;
  referencedColumns: string[];
}

export interface QueryResult {
  rows: any[];
  rowCount: number;
  fields: { name: string; type: string }[];
  executionTime: number;
}

export interface NLQueryResult {
  /** Natural language query */
  query: string;
  /** Generated SQL */
  sql: string;
  /** Query result */
  result: QueryResult;
  /** Explanation of the query */
  explanation?: string;
}

/**
 * Create a Natural Language Postgres client.
 * 
 * @example Basic usage
 * ```typescript
 * import { createNLPostgres } from 'praisonai/integrations/postgres';
 * 
 * const db = await createNLPostgres({
 *   connectionUrl: process.env.DATABASE_URL!,
 *   readOnly: true
 * });
 * 
 * // Query with natural language
 * const result = await db.query('Show me all users who signed up last month');
 * console.log(result.rows);
 * ```
 * 
 * @example With schema introspection
 * ```typescript
 * const db = await createNLPostgres({ connectionUrl: '...' });
 * 
 * // Get schema information
 * const schema = await db.getSchema();
 * console.log('Tables:', schema.map(t => t.name));
 * 
 * // Query with context
 * const result = await db.query('How many orders were placed today?');
 * ```
 */
export async function createNLPostgres(config: PostgresConfig): Promise<NLPostgresClient> {
  const client = new NLPostgresClient(config);
  await client.connect();
  return client;
}

export class NLPostgresClient {
  private config: PostgresConfig;
  private pool: any = null;
  private schema: TableSchema[] = [];
  private connected = false;

  constructor(config: PostgresConfig) {
    this.config = {
      schema: 'public',
      readOnly: true,
      maxRows: 100,
      timeout: 30000,
      ...config,
    };
  }

  /**
   * Connect to the database.
   */
  async connect(): Promise<void> {
    if (this.connected) return;

    try {
      // @ts-ignore - Optional dependency
      const { Pool } = await import('pg');
      this.pool = new Pool({
        connectionString: this.config.connectionUrl,
        statement_timeout: this.config.timeout,
      });

      // Test connection
      await this.pool.query('SELECT 1');
      this.connected = true;

      // Load schema
      await this.loadSchema();
    } catch (error: any) {
      throw new Error(
        `Failed to connect to PostgreSQL: ${error.message}. ` +
        'Install with: npm install pg'
      );
    }
  }

  /**
   * Disconnect from the database.
   */
  async disconnect(): Promise<void> {
    if (this.pool) {
      await this.pool.end();
      this.connected = false;
    }
  }

  /**
   * Load database schema.
   */
  private async loadSchema(): Promise<void> {
    const schemaQuery = `
      SELECT 
        t.table_name,
        c.column_name,
        c.data_type,
        c.is_nullable,
        c.column_default,
        pgd.description
      FROM information_schema.tables t
      JOIN information_schema.columns c 
        ON t.table_name = c.table_name 
        AND t.table_schema = c.table_schema
      LEFT JOIN pg_catalog.pg_statio_all_tables st
        ON st.relname = t.table_name
      LEFT JOIN pg_catalog.pg_description pgd
        ON pgd.objoid = st.relid
        AND pgd.objsubid = c.ordinal_position
      WHERE t.table_schema = $1
        AND t.table_type = 'BASE TABLE'
      ORDER BY t.table_name, c.ordinal_position
    `;

    const result = await this.pool.query(schemaQuery, [this.config.schema]);
    
    const tableMap = new Map<string, TableSchema>();
    
    for (const row of result.rows) {
      // Check allowed/blocked tables
      if (this.config.allowedTables && !this.config.allowedTables.includes(row.table_name)) {
        continue;
      }
      if (this.config.blockedTables && this.config.blockedTables.includes(row.table_name)) {
        continue;
      }

      if (!tableMap.has(row.table_name)) {
        tableMap.set(row.table_name, {
          name: row.table_name,
          columns: [],
        });
      }

      const table = tableMap.get(row.table_name)!;
      table.columns.push({
        name: row.column_name,
        type: row.data_type,
        nullable: row.is_nullable === 'YES',
        defaultValue: row.column_default,
        description: row.description,
      });
    }

    this.schema = Array.from(tableMap.values());
  }

  /**
   * Get the database schema.
   */
  getSchema(): TableSchema[] {
    return this.schema;
  }

  /**
   * Get schema as a string for LLM context.
   */
  getSchemaContext(): string {
    let context = 'Database Schema:\n\n';
    
    for (const table of this.schema) {
      context += `Table: ${table.name}\n`;
      context += 'Columns:\n';
      for (const col of table.columns) {
        context += `  - ${col.name} (${col.type}${col.nullable ? ', nullable' : ''})`;
        if (col.description) {
          context += ` - ${col.description}`;
        }
        context += '\n';
      }
      context += '\n';
    }
    
    return context;
  }

  /**
   * Execute a raw SQL query.
   */
  async executeSQL(sql: string): Promise<QueryResult> {
    if (!this.connected) {
      throw new Error('Not connected to database');
    }

    // Safety check for read-only mode
    if (this.config.readOnly) {
      const normalizedSQL = sql.trim().toLowerCase();
      const writeOperations = ['insert', 'update', 'delete', 'drop', 'alter', 'create', 'truncate'];
      
      for (const op of writeOperations) {
        if (normalizedSQL.startsWith(op)) {
          throw new Error(`Write operation '${op}' not allowed in read-only mode`);
        }
      }
    }

    // Add LIMIT if not present
    const hasLimit = /\blimit\s+\d+/i.test(sql);
    const finalSQL = hasLimit ? sql : `${sql} LIMIT ${this.config.maxRows}`;

    const startTime = Date.now();
    const result = await this.pool.query(finalSQL);
    const executionTime = Date.now() - startTime;

    return {
      rows: result.rows,
      rowCount: result.rowCount,
      fields: result.fields?.map((f: any) => ({ name: f.name, type: f.dataTypeID?.toString() })) || [],
      executionTime,
    };
  }

  /**
   * Query the database using natural language.
   */
  async query(naturalLanguageQuery: string, options?: { model?: string }): Promise<NLQueryResult> {
    const model = options?.model || 'gpt-4o-mini';
    
    // Generate SQL from natural language
    const { generateText } = await import('../ai/generate-text');
    
    const schemaContext = this.getSchemaContext();
    const prompt = `You are a SQL expert. Convert the following natural language query to PostgreSQL SQL.

${schemaContext}

Rules:
1. Only generate SELECT queries (read-only)
2. Use proper PostgreSQL syntax
3. Include appropriate JOINs when needed
4. Add reasonable LIMIT if not specified
5. Return ONLY the SQL query, no explanations

Natural language query: ${naturalLanguageQuery}

SQL:`;

    const result = await generateText({
      model,
      prompt,
      temperature: 0,
    });

    // Extract SQL from response
    let sql = result.text.trim();
    
    // Remove markdown code blocks if present
    if (sql.startsWith('```')) {
      sql = sql.replace(/```sql?\n?/g, '').replace(/```/g, '').trim();
    }

    // Execute the SQL
    const queryResult = await this.executeSQL(sql);

    return {
      query: naturalLanguageQuery,
      sql,
      result: queryResult,
    };
  }

  /**
   * Chat with the database (conversational interface).
   */
  async chat(message: string, options?: { model?: string; history?: Array<{ role: string; content: string }> }): Promise<string> {
    const model = options?.model || 'gpt-4o-mini';
    const history = options?.history || [];
    
    const { generateText } = await import('../ai/generate-text');
    
    const schemaContext = this.getSchemaContext();
    const systemPrompt = `You are a helpful database assistant. You can query a PostgreSQL database to answer questions.

${schemaContext}

When the user asks a question that requires database data:
1. Generate a SQL query to get the data
2. Execute it using the query tool
3. Summarize the results in natural language

Always be helpful and explain your findings clearly.`;

    const messages: Array<{ role: 'system' | 'user' | 'assistant'; content: string }> = [
      { role: 'system', content: systemPrompt },
      ...history.map(h => ({ role: h.role as 'user' | 'assistant', content: h.content })),
      { role: 'user', content: message },
    ];

    // Define the query tool
    const tools = {
      query_database: {
        description: 'Execute a SQL query on the PostgreSQL database',
        parameters: {
          type: 'object',
          properties: {
            sql: {
              type: 'string',
              description: 'The SQL query to execute (SELECT only)',
            },
          },
          required: ['sql'],
        },
        execute: async ({ sql }: { sql: string }) => {
          try {
            const result = await this.executeSQL(sql);
            return JSON.stringify({
              rowCount: result.rowCount,
              rows: result.rows.slice(0, 10), // Limit for context
              hasMore: result.rowCount > 10,
            });
          } catch (error: any) {
            return JSON.stringify({ error: error.message });
          }
        },
      },
    };

    const result = await generateText({
      model,
      messages,
      tools,
      maxSteps: 3,
    });

    return result.text;
  }

  /**
   * Inspect the database structure.
   */
  async inspect(): Promise<{
    tables: number;
    schema: TableSchema[];
    sampleData: Record<string, any[]>;
  }> {
    const sampleData: Record<string, any[]> = {};
    
    for (const table of this.schema) {
      try {
        const result = await this.executeSQL(`SELECT * FROM ${table.name} LIMIT 3`);
        sampleData[table.name] = result.rows;
      } catch {
        sampleData[table.name] = [];
      }
    }

    return {
      tables: this.schema.length,
      schema: this.schema,
      sampleData,
    };
  }
}

/**
 * Create a tool for querying Postgres with natural language.
 * 
 * @example Use with an agent
 * ```typescript
 * import { Agent } from 'praisonai';
 * import { createPostgresTool } from 'praisonai/integrations/postgres';
 * 
 * const dbTool = await createPostgresTool({
 *   connectionUrl: process.env.DATABASE_URL!
 * });
 * 
 * const agent = new Agent({
 *   instructions: 'You can query the database',
 *   tools: [dbTool]
 * });
 * ```
 */
export async function createPostgresTool(config: PostgresConfig): Promise<any> {
  const client = await createNLPostgres(config);
  
  return {
    name: 'query_database',
    description: `Query the PostgreSQL database using natural language. Available tables: ${client.getSchema().map(t => t.name).join(', ')}`,
    parameters: {
      type: 'object',
      properties: {
        query: {
          type: 'string',
          description: 'Natural language query describing what data you want',
        },
      },
      required: ['query'],
    },
    execute: async ({ query }: { query: string }) => {
      const result = await client.query(query);
      return JSON.stringify({
        sql: result.sql,
        rowCount: result.result.rowCount,
        rows: result.result.rows,
      });
    },
  };
}
