//! Procedural macros for PraisonAI
//!
//! This crate provides the `#[tool]` attribute macro for defining tools.
//!
//! # Example
//!
//! ```rust,ignore
//! use praisonai::tool;
//!
//! #[tool(description = "Search the web for information")]
//! async fn search_web(query: String) -> String {
//!     format!("Results for: {}", query)
//! }
//! ```

use proc_macro::TokenStream;
use quote::{quote, format_ident};
use syn::{parse_macro_input, ItemFn, Lit, Meta, Expr, ExprLit};

/// The `#[tool]` attribute macro for defining tools.
///
/// This macro transforms a function into a tool that can be used by agents.
///
/// # Attributes
///
/// - `description`: A description of what the tool does (required for LLM understanding)
/// - `name`: Override the tool name (defaults to function name)
///
/// # Example
///
/// ```rust,ignore
/// use praisonai::tool;
///
/// #[tool(description = "Search the web")]
/// async fn search(query: String) -> String {
///     format!("Results for: {}", query)
/// }
///
/// // With custom name
/// #[tool(name = "web_search", description = "Search the internet")]
/// async fn my_search_fn(query: String, max_results: u32) -> Vec<String> {
///     vec![format!("Result for: {}", query)]
/// }
/// ```
#[proc_macro_attribute]
pub fn tool(attr: TokenStream, item: TokenStream) -> TokenStream {
    let input_fn = parse_macro_input!(item as ItemFn);
    
    // Extract attributes from the attr token stream
    let mut description = String::new();
    let mut custom_name: Option<String> = None;
    
    // Parse attributes manually for syn 2.x
    let attr_parser = syn::meta::parser(|meta| {
        if meta.path.is_ident("description") {
            let value: syn::LitStr = meta.value()?.parse()?;
            description = value.value();
            Ok(())
        } else if meta.path.is_ident("name") {
            let value: syn::LitStr = meta.value()?.parse()?;
            custom_name = Some(value.value());
            Ok(())
        } else {
            Err(meta.error("unsupported attribute"))
        }
    });
    
    parse_macro_input!(attr with attr_parser);
    
    // Get function details
    let fn_name = &input_fn.sig.ident;
    let fn_vis = &input_fn.vis;
    let fn_block = &input_fn.block;
    let fn_inputs = &input_fn.sig.inputs;
    let fn_output = &input_fn.sig.output;
    let fn_asyncness = &input_fn.sig.asyncness;
    
    // Tool name (custom or function name)
    let tool_name = custom_name.unwrap_or_else(|| fn_name.to_string());
    
    // Use docstring as description if not provided
    let description = if description.is_empty() {
        // Try to extract from doc comments
        let mut doc = String::new();
        for attr in &input_fn.attrs {
            if attr.path().is_ident("doc") {
                if let Meta::NameValue(nv) = &attr.meta {
                    if let Expr::Lit(ExprLit { lit: Lit::Str(lit), .. }) = &nv.value {
                        if !doc.is_empty() {
                            doc.push(' ');
                        }
                        doc.push_str(lit.value().trim());
                    }
                }
            }
        }
        if doc.is_empty() {
            format!("Tool: {}", tool_name)
        } else {
            doc
        }
    } else {
        description
    };
    
    // Generate parameter schema
    let mut param_names: Vec<syn::Ident> = Vec::new();
    let mut param_types: Vec<syn::Type> = Vec::new();
    let mut param_name_strs: Vec<String> = Vec::new();
    let mut param_json_types: Vec<String> = Vec::new();
    
    for input in fn_inputs.iter() {
        if let syn::FnArg::Typed(pat_type) = input {
            if let syn::Pat::Ident(pat_ident) = &*pat_type.pat {
                let name = pat_ident.ident.clone();
                let name_str = name.to_string();
                let ty = (*pat_type.ty).clone();
                
                // Map Rust types to JSON Schema types
                let json_type = rust_type_to_json_schema(&pat_type.ty);
                
                param_names.push(name);
                param_name_strs.push(name_str);
                param_types.push(ty);
                param_json_types.push(json_type);
            }
        }
    }
    
    // Generate the struct name for the tool
    let struct_name = format_ident!("{}Tool", to_pascal_case(&tool_name));
    
    // Generate the implementation
    let expanded = quote! {
        // Keep the original function
        #fn_vis #fn_asyncness fn #fn_name(#fn_inputs) #fn_output #fn_block
        
        /// Auto-generated tool struct for #fn_name
        #[derive(Debug, Clone)]
        #fn_vis struct #struct_name;
        
        impl #struct_name {
            /// Create a new instance of this tool
            pub fn new() -> Self {
                Self
            }
        }
        
        impl Default for #struct_name {
            fn default() -> Self {
                Self::new()
            }
        }
        
        #[async_trait::async_trait]
        impl praisonai::Tool for #struct_name {
            fn name(&self) -> &str {
                #tool_name
            }
            
            fn description(&self) -> &str {
                #description
            }
            
            fn parameters_schema(&self) -> serde_json::Value {
                let mut properties = serde_json::Map::new();
                let mut required = Vec::new();
                
                #(
                    properties.insert(
                        #param_name_strs.to_string(),
                        serde_json::json!({ "type": #param_json_types })
                    );
                    required.push(serde_json::Value::String(#param_name_strs.to_string()));
                )*
                
                serde_json::json!({
                    "type": "object",
                    "properties": properties,
                    "required": required
                })
            }
            
            async fn execute(&self, args: serde_json::Value) -> praisonai::Result<serde_json::Value> {
                #(
                    let #param_names: #param_types = serde_json::from_value(
                        args.get(#param_name_strs)
                            .cloned()
                            .unwrap_or(serde_json::Value::Null)
                    ).map_err(|e| praisonai::Error::tool(format!("Failed to parse {}: {}", #param_name_strs, e)))?;
                )*
                
                let result = #fn_name(#(#param_names),*).await;
                serde_json::to_value(result)
                    .map_err(|e| praisonai::Error::tool(format!("Failed to serialize result: {}", e)))
            }
        }
    };
    
    TokenStream::from(expanded)
}

/// Convert a Rust type to JSON Schema type string
fn rust_type_to_json_schema(ty: &syn::Type) -> String {
    let type_str = quote!(#ty).to_string().replace(" ", "");
    
    match type_str.as_str() {
        "String" | "&str" | "str" => "string".to_string(),
        "i8" | "i16" | "i32" | "i64" | "i128" | "isize" |
        "u8" | "u16" | "u32" | "u64" | "u128" | "usize" => "integer".to_string(),
        "f32" | "f64" => "number".to_string(),
        "bool" => "boolean".to_string(),
        _ if type_str.starts_with("Vec<") => "array".to_string(),
        _ if type_str.starts_with("Option<") => {
            // Extract inner type
            let inner = &type_str[7..type_str.len()-1];
            rust_type_str_to_json_schema(inner)
        }
        _ => "object".to_string(),
    }
}

fn rust_type_str_to_json_schema(type_str: &str) -> String {
    match type_str {
        "String" | "&str" | "str" => "string".to_string(),
        "i8" | "i16" | "i32" | "i64" | "i128" | "isize" |
        "u8" | "u16" | "u32" | "u64" | "u128" | "usize" => "integer".to_string(),
        "f32" | "f64" => "number".to_string(),
        "bool" => "boolean".to_string(),
        _ if type_str.starts_with("Vec<") => "array".to_string(),
        _ => "object".to_string(),
    }
}

/// Convert snake_case to PascalCase
fn to_pascal_case(s: &str) -> String {
    s.split('_')
        .map(|word| {
            let mut chars = word.chars();
            match chars.next() {
                None => String::new(),
                Some(first) => first.to_uppercase().chain(chars).collect(),
            }
        })
        .collect()
}
