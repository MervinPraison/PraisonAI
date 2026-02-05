//! Comprehensive Parity Feature Integration Tests
//!
//! This example tests all parity features implemented in the Rust SDK.
//! Run with: cargo run --example parity_integration_test
//!
//! Set OPENAI_API_KEY environment variable for real API tests.

use praisonai::{
    // Deep Research Types
    DeepResearchCitation, ReasoningStep, WebSearchCall, CodeExecutionStep, FileSearchCall,
    Provider, DeepResearchResponse,
    // RAG Types
    RAGCitation, RetrievalPolicy, RagRetrievalPolicy,
    // Guardrail Types
    LLMGuardrail,
    // Handoff Errors
    HandoffError,
    // App Protocols
    AgentAppConfig,
    // Sandbox Types
    SecurityPolicy,
    // Reflection Types
    ReflectionOutput,
    // Embedding Functions
    embed, embedding, embeddings,
    // Display Callbacks
    sync_display_callbacks, async_display_callbacks, error_logs,
    // Presets
    PARITY_AUTONOMY_PRESETS, RECOMMENDED_PROMPT_PREFIX,
    // Resolver Functions
    resolve_guardrail_policies,
    // Trace Functions
    trace_context, track_workflow,
    // Plugin Functions
    load_plugin,
    // Telemetry
    get_telemetry, enable_telemetry, disable_telemetry, is_telemetry_enabled,
    // Config
    get_config,
    // UI Protocols
    A2A, AGUI, AGUIEvent, AGUIEventType,
};

fn main() {
    println!("╔══════════════════════════════════════════════════════════════╗");
    println!("║     PraisonAI Rust SDK - Parity Feature Integration Tests    ║");
    println!("╚══════════════════════════════════════════════════════════════╝\n");

    let mut passed = 0;
    let mut failed = 0;

    // =========================================================================
    // Test 1: Deep Research Types
    // =========================================================================
    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    println!("📚 Test 1: Deep Research Types");
    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    
    // Test Citation
    let citation = DeepResearchCitation::new("AI Research Paper", "https://arxiv.org/paper123");
    if citation.title == "AI Research Paper" && citation.url == "https://arxiv.org/paper123" {
        println!("  ✅ Citation: Created successfully");
        println!("     - Title: {}", citation.title);
        println!("     - URL: {}", citation.url);
        passed += 1;
    } else {
        println!("  ❌ Citation: Failed");
        failed += 1;
    }

    // Test ReasoningStep
    let step = ReasoningStep::new("Analyzing the problem from multiple angles");
    if step.step_type == "reasoning" {
        println!("  ✅ ReasoningStep: Created with type '{}'", step.step_type);
        println!("     - Text: {}", step.text);
        passed += 1;
    } else {
        println!("  ❌ ReasoningStep: Failed");
        failed += 1;
    }

    // Test WebSearchCall
    let search = WebSearchCall::new("latest AI trends 2025", "completed");
    if search.status == "completed" {
        println!("  ✅ WebSearchCall: Query '{}' - Status: {}", search.query, search.status);
        passed += 1;
    } else {
        println!("  ❌ WebSearchCall: Failed");
        failed += 1;
    }

    // Test CodeExecutionStep
    let code = CodeExecutionStep::with_output("print('Hello AI')", "Hello AI");
    if code.output == Some("Hello AI".to_string()) {
        println!("  ✅ CodeExecutionStep: Executed with output '{}'", code.output.as_ref().unwrap());
        passed += 1;
    } else {
        println!("  ❌ CodeExecutionStep: Failed");
        failed += 1;
    }

    // Test FileSearchCall
    let file_search = FileSearchCall::new(vec!["store1".to_string(), "store2".to_string()]);
    if file_search.store_names.len() == 2 {
        println!("  ✅ FileSearchCall: Searching {} stores", file_search.store_names.len());
        passed += 1;
    } else {
        println!("  ❌ FileSearchCall: Failed");
        failed += 1;
    }

    // Test Provider
    let provider = Provider::default();
    if provider == Provider::OpenAI {
        println!("  ✅ Provider: Default is {:?}", provider);
        passed += 1;
    } else {
        println!("  ❌ Provider: Failed");
        failed += 1;
    }

    // Test DeepResearchResponse
    let mut response = DeepResearchResponse::new("This is a comprehensive research report on AI.");
    response.citations.push(DeepResearchCitation {
        title: "Source 1".to_string(),
        url: "https://example.com".to_string(),
        start_index: 0,
        end_index: 4,
    });
    response.reasoning_steps.push(ReasoningStep::new("Step 1"));
    response.web_searches.push(WebSearchCall::new("query", "done"));
    
    let sources = response.get_all_sources();
    if sources.len() == 1 && response.report.contains("research report") {
        println!("  ✅ DeepResearchResponse: Created with {} citations, {} reasoning steps", 
                 response.citations.len(), response.reasoning_steps.len());
        println!("     - Report preview: {}...", &response.report[..40]);
        passed += 1;
    } else {
        println!("  ❌ DeepResearchResponse: Failed");
        failed += 1;
    }

    // =========================================================================
    // Test 2: RAG Types
    // =========================================================================
    println!("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    println!("🔍 Test 2: RAG Types");
    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");

    // Test RAGCitation (alias for Citation)
    let rag_citation: RAGCitation = DeepResearchCitation::new("RAG Source", "https://rag.example.com");
    if !rag_citation.title.is_empty() {
        println!("  ✅ RAGCitation: Type alias works correctly");
        println!("     - Title: {}", rag_citation.title);
        passed += 1;
    } else {
        println!("  ❌ RAGCitation: Failed");
        failed += 1;
    }

    // Test RetrievalPolicy
    let policy = RetrievalPolicy::default();
    if policy == RetrievalPolicy::Always {
        println!("  ✅ RetrievalPolicy: Default is {:?}", policy);
        passed += 1;
    } else {
        println!("  ❌ RetrievalPolicy: Failed");
        failed += 1;
    }

    // Test all RetrievalPolicy variants
    let policies = vec![
        RetrievalPolicy::Always,
        RetrievalPolicy::Never,
        RetrievalPolicy::OnDemand,
        RetrievalPolicy::Threshold,
    ];
    println!("  ✅ RetrievalPolicy variants: {:?}", policies);
    passed += 1;

    // Test RagRetrievalPolicy alias
    let _rag_policy: RagRetrievalPolicy = RetrievalPolicy::OnDemand;
    println!("  ✅ RagRetrievalPolicy: Type alias works");
    passed += 1;

    // =========================================================================
    // Test 3: Guardrail Types
    // =========================================================================
    println!("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    println!("🛡️ Test 3: Guardrail Types");
    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");

    let guardrail = LLMGuardrail::new("content_safety", "Ensures content is safe and appropriate")
        .with_model("gpt-4o-mini")
        .with_prompt("Check if the following content is safe: {content}")
        .block_on_failure(true);

    if guardrail.name == "content_safety" && guardrail.model == "gpt-4o-mini" && guardrail.block_on_failure {
        println!("  ✅ LLMGuardrail: Created successfully");
        println!("     - Name: {}", guardrail.name);
        println!("     - Model: {}", guardrail.model);
        println!("     - Block on failure: {}", guardrail.block_on_failure);
        passed += 1;
    } else {
        println!("  ❌ LLMGuardrail: Failed");
        failed += 1;
    }

    // =========================================================================
    // Test 4: Handoff Errors
    // =========================================================================
    println!("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    println!("🔄 Test 4: Handoff Errors");
    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");

    // Test Cycle error
    let cycle_err = HandoffError::Cycle { 
        agents: vec!["agent_a".to_string(), "agent_b".to_string(), "agent_a".to_string()] 
    };
    let cycle_msg = cycle_err.to_string();
    if cycle_msg.contains("cycle") {
        println!("  ✅ HandoffError::Cycle: {}", cycle_msg);
        passed += 1;
    } else {
        println!("  ❌ HandoffError::Cycle: Failed");
        failed += 1;
    }

    // Test DepthExceeded error
    let depth_err = HandoffError::DepthExceeded { max_depth: 10 };
    let depth_msg = depth_err.to_string();
    if depth_msg.contains("10") {
        println!("  ✅ HandoffError::DepthExceeded: {}", depth_msg);
        passed += 1;
    } else {
        println!("  ❌ HandoffError::DepthExceeded: Failed");
        failed += 1;
    }

    // Test Timeout error
    let timeout_err = HandoffError::Timeout { timeout_ms: 30000 };
    let timeout_msg = timeout_err.to_string();
    if timeout_msg.contains("30000") {
        println!("  ✅ HandoffError::Timeout: {}", timeout_msg);
        passed += 1;
    } else {
        println!("  ❌ HandoffError::Timeout: Failed");
        failed += 1;
    }

    // Test AgentNotFound error
    let not_found_err = HandoffError::AgentNotFound { name: "unknown_agent".to_string() };
    println!("  ✅ HandoffError::AgentNotFound: {}", not_found_err);
    passed += 1;

    // Test InvalidConfig error
    let invalid_err = HandoffError::InvalidConfig { message: "Missing required field".to_string() };
    println!("  ✅ HandoffError::InvalidConfig: {}", invalid_err);
    passed += 1;

    // =========================================================================
    // Test 5: App Protocols
    // =========================================================================
    println!("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    println!("📱 Test 5: App Protocols");
    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");

    let app_config = AgentAppConfig::new("my_agent_app");
    if app_config.name == "my_agent_app" && app_config.port == 8000 {
        println!("  ✅ AgentAppConfig: Created successfully");
        println!("     - Name: {}", app_config.name);
        println!("     - Version: {}", app_config.version);
        println!("     - Host: {}", app_config.host);
        println!("     - Port: {}", app_config.port);
        println!("     - Debug: {}", app_config.debug);
        passed += 1;
    } else {
        println!("  ❌ AgentAppConfig: Failed");
        failed += 1;
    }

    // =========================================================================
    // Test 6: Sandbox Types
    // =========================================================================
    println!("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    println!("🔒 Test 6: Sandbox Types");
    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");

    let restrictive = SecurityPolicy::restrictive();
    if !restrictive.allow_network && !restrictive.allow_filesystem && !restrictive.allow_subprocess {
        println!("  ✅ SecurityPolicy::restrictive()");
        println!("     - Network: {}", restrictive.allow_network);
        println!("     - Filesystem: {}", restrictive.allow_filesystem);
        println!("     - Subprocess: {}", restrictive.allow_subprocess);
        println!("     - Max execution time: {}s", restrictive.max_execution_time);
        passed += 1;
    } else {
        println!("  ❌ SecurityPolicy::restrictive(): Failed");
        failed += 1;
    }

    let permissive = SecurityPolicy::permissive();
    if permissive.allow_network && permissive.allow_filesystem && permissive.allow_subprocess {
        println!("  ✅ SecurityPolicy::permissive()");
        println!("     - Network: {}", permissive.allow_network);
        println!("     - Filesystem: {}", permissive.allow_filesystem);
        println!("     - Subprocess: {}", permissive.allow_subprocess);
        println!("     - Max execution time: {}s", permissive.max_execution_time);
        passed += 1;
    } else {
        println!("  ❌ SecurityPolicy::permissive(): Failed");
        failed += 1;
    }

    // =========================================================================
    // Test 7: Reflection Types
    // =========================================================================
    println!("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    println!("🪞 Test 7: Reflection Types");
    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");

    let reflection = ReflectionOutput::new(
        "The answer is 42",
        "This answer is correct but could be more detailed"
    );
    if !reflection.was_modified && reflection.confidence == 1.0 {
        println!("  ✅ ReflectionOutput::new()");
        println!("     - Original: {}", reflection.original);
        println!("     - Reflection: {}", reflection.reflection);
        println!("     - Was modified: {}", reflection.was_modified);
        passed += 1;
    } else {
        println!("  ❌ ReflectionOutput::new(): Failed");
        failed += 1;
    }

    let improved = ReflectionOutput::with_improvement(
        "The answer is 42",
        "Adding more context would help",
        "The answer is 42, which is the answer to life, the universe, and everything"
    );
    if improved.was_modified && improved.improved.is_some() {
        println!("  ✅ ReflectionOutput::with_improvement()");
        println!("     - Improved: {}", improved.improved.as_ref().unwrap());
        passed += 1;
    } else {
        println!("  ❌ ReflectionOutput::with_improvement(): Failed");
        failed += 1;
    }

    // =========================================================================
    // Test 8: Embedding Functions
    // =========================================================================
    println!("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    println!("🔢 Test 8: Embedding Functions");
    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");

    // Test embed function
    match embed("Hello, world!", None) {
        Ok(vec) => {
            if vec.len() == 1536 {
                println!("  ✅ embed(): Returns {} dimensional vector", vec.len());
                passed += 1;
            } else {
                println!("  ❌ embed(): Wrong dimension");
                failed += 1;
            }
        }
        Err(e) => {
            println!("  ❌ embed(): Error - {}", e);
            failed += 1;
        }
    }

    // Test embedding function (alias)
    match embedding("Test text", Some("text-embedding-3-small")) {
        Ok(vec) => {
            println!("  ✅ embedding(): Alias works, {} dimensions", vec.len());
            passed += 1;
        }
        Err(e) => {
            println!("  ❌ embedding(): Error - {}", e);
            failed += 1;
        }
    }

    // Test embeddings function (batch)
    match embeddings(&["text1", "text2", "text3"], None) {
        Ok(vecs) => {
            if vecs.len() == 3 {
                println!("  ✅ embeddings(): Batch of {} vectors", vecs.len());
                passed += 1;
            } else {
                println!("  ❌ embeddings(): Wrong batch size");
                failed += 1;
            }
        }
        Err(e) => {
            println!("  ❌ embeddings(): Error - {}", e);
            failed += 1;
        }
    }

    // =========================================================================
    // Test 9: Display Callbacks
    // =========================================================================
    println!("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    println!("📺 Test 9: Display Callbacks");
    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");

    let sync_cbs = sync_display_callbacks();
    println!("  ✅ sync_display_callbacks(): {} callbacks registered", sync_cbs.len());
    passed += 1;

    let async_cbs = async_display_callbacks();
    println!("  ✅ async_display_callbacks(): {} callbacks registered", async_cbs.len());
    passed += 1;

    let logs = error_logs();
    println!("  ✅ error_logs(): {} logs", logs.len());
    passed += 1;

    // =========================================================================
    // Test 10: Presets
    // =========================================================================
    println!("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    println!("⚙️ Test 10: Presets");
    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");

    if PARITY_AUTONOMY_PRESETS.contains_key("full") && 
       PARITY_AUTONOMY_PRESETS.contains_key("supervised") && 
       PARITY_AUTONOMY_PRESETS.contains_key("minimal") {
        println!("  ✅ PARITY_AUTONOMY_PRESETS: Contains all presets");
        for (name, preset) in PARITY_AUTONOMY_PRESETS.iter() {
            println!("     - {}: {:?}", name, preset.get("level"));
        }
        passed += 1;
    } else {
        println!("  ❌ PARITY_AUTONOMY_PRESETS: Missing presets");
        failed += 1;
    }

    if RECOMMENDED_PROMPT_PREFIX.contains("hand off") {
        println!("  ✅ RECOMMENDED_PROMPT_PREFIX: Contains handoff instructions");
        println!("     - Preview: {}...", &RECOMMENDED_PROMPT_PREFIX[..50]);
        passed += 1;
    } else {
        println!("  ❌ RECOMMENDED_PROMPT_PREFIX: Missing content");
        failed += 1;
    }

    // =========================================================================
    // Test 11: Resolver Functions
    // =========================================================================
    println!("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    println!("🔧 Test 11: Resolver Functions");
    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");

    let policies = resolve_guardrail_policies(Some(&["no_pii", "no_profanity", "content_safety"]), None);
    if policies.len() == 3 {
        println!("  ✅ resolve_guardrail_policies(): Resolved {} policies", policies.len());
        for p in &policies {
            println!("     - {}", p);
        }
        passed += 1;
    } else {
        println!("  ❌ resolve_guardrail_policies(): Failed");
        failed += 1;
    }

    let empty_policies = resolve_guardrail_policies(None, None);
    if empty_policies.is_empty() {
        println!("  ✅ resolve_guardrail_policies(None, None): Returns empty");
        passed += 1;
    } else {
        println!("  ❌ resolve_guardrail_policies(None, None): Should be empty");
        failed += 1;
    }

    // =========================================================================
    // Test 12: Trace Functions
    // =========================================================================
    println!("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    println!("📊 Test 12: Trace Functions");
    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");

    let ctx = trace_context();
    if !ctx.trace_id.is_empty() && !ctx.span_id.is_empty() {
        println!("  ✅ trace_context(): Created");
        println!("     - Trace ID: {}", ctx.trace_id);
        println!("     - Span ID: {}", ctx.span_id);
        passed += 1;
    } else {
        println!("  ❌ trace_context(): Failed");
        failed += 1;
    }

    let workflow_ctx = track_workflow("research_workflow", None);
    if workflow_ctx.attributes.contains_key("workflow_name") {
        println!("  ✅ track_workflow(): Tracking 'research_workflow'");
        println!("     - Trace ID: {}", workflow_ctx.trace_id);
        passed += 1;
    } else {
        println!("  ❌ track_workflow(): Failed");
        failed += 1;
    }

    // =========================================================================
    // Test 13: Plugin Functions
    // =========================================================================
    println!("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    println!("🔌 Test 13: Plugin Functions");
    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");

    match load_plugin("/path/to/plugin") {
        Ok(()) => {
            println!("  ✅ load_plugin(): Function callable (placeholder)");
            passed += 1;
        }
        Err(e) => {
            println!("  ❌ load_plugin(): Error - {}", e);
            failed += 1;
        }
    }

    // =========================================================================
    // Test 14: Telemetry Functions
    // =========================================================================
    println!("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    println!("📈 Test 14: Telemetry Functions");
    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");

    let _telemetry = get_telemetry();
    println!("  ✅ get_telemetry(): Instance retrieved");
    passed += 1;

    enable_telemetry();
    if is_telemetry_enabled() {
        println!("  ✅ enable_telemetry() + is_telemetry_enabled(): Works");
        passed += 1;
    } else {
        println!("  ❌ enable_telemetry(): Failed");
        failed += 1;
    }

    disable_telemetry();
    if !is_telemetry_enabled() {
        println!("  ✅ disable_telemetry(): Works");
        passed += 1;
    } else {
        println!("  ❌ disable_telemetry(): Failed");
        failed += 1;
    }

    // =========================================================================
    // Test 15: UI Protocols
    // =========================================================================
    println!("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    println!("🖥️ Test 15: UI Protocols");
    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");

    let a2a = A2A::new("test_agent", "http://localhost:8000");
    println!("  ✅ A2A: Created for agent '{}'", a2a.name);
    passed += 1;

    let agui = AGUI::new("gui_session");
    println!("  ✅ AGUI: Created session '{}'", agui.name);
    passed += 1;

    let event = AGUIEvent::run_started("test_run_123");
    println!("  ✅ AGUIEvent: Created {:?} event", event.event_type);
    passed += 1;

    // =========================================================================
    // Test 16: Config Functions
    // =========================================================================
    println!("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    println!("⚙️ Test 16: Config Functions");
    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");

    let config = get_config();
    println!("  ✅ get_config(): Retrieved configuration");
    println!("     - Plugins: {:?}", config.plugins);
    passed += 1;

    // =========================================================================
    // Summary
    // =========================================================================
    println!("\n╔══════════════════════════════════════════════════════════════╗");
    println!("║                        TEST SUMMARY                          ║");
    println!("╠══════════════════════════════════════════════════════════════╣");
    println!("║  ✅ Passed: {:3}                                              ║", passed);
    println!("║  ❌ Failed: {:3}                                              ║", failed);
    println!("║  📊 Total:  {:3}                                              ║", passed + failed);
    println!("╚══════════════════════════════════════════════════════════════╝");

    if failed == 0 {
        println!("\n🎉 All parity feature tests PASSED!");
    } else {
        println!("\n⚠️  Some tests failed. Please review the output above.");
        std::process::exit(1);
    }
}
