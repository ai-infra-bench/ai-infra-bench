use serde_json::{json, Value};
use vllm_tool_parser::{
    DeepSeekV32ToolParser, Glm45MoeToolParser, MinimaxM2ToolParser,
    Qwen3CoderToolParser, Tool, ToolParser, ToolParserOutput,
};

fn default_tools() -> Vec<Tool> {
    vec![
        Tool {
            name: "write_file".to_string(),
            description: Some("Write a file".to_string()),
            parameters: json!({
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "count": {"type": "integer"},
                    "flag": {"type": "boolean"},
                    "payload": {"type": "object"},
                    "items": {"type": "array"},
                    "empty": {"type": "null"}
                },
                "required": ["content"]
            }),
            strict: None,
        },
        Tool {
            name: "edit".to_string(),
            description: Some("Modify an existing file using exact strings".to_string()),
            parameters: json!({
                "type": "object",
                "properties": {
                    "filePath": {"type": "string"},
                    "oldString": {"type": "string"},
                    "newString": {"type": "string"},
                    "replaceAll": {"type": "boolean"}
                },
                "required": ["filePath", "oldString", "newString"]
            }),
            strict: None,
        },
    ]
}

fn parser(name: &str, tools: &[Tool]) -> Box<dyn ToolParser> {
    match name {
        "minimax_m2" => MinimaxM2ToolParser::create(tools).unwrap(),
        "qwen_coder" => Qwen3CoderToolParser::create(tools).unwrap(),
        "glm_xml" => Glm45MoeToolParser::create(tools).unwrap(),
        "deepseek_dsml" => DeepSeekV32ToolParser::create(tools).unwrap(),
        other => panic!("unknown parser: {other}"),
    }
}

fn stream_chunks(wire: &str, sizes: &[usize]) -> Vec<String> {
    let characters = wire.chars().collect::<Vec<_>>();
    let mut chunks = Vec::new();
    let mut offset = 0;
    let mut size_index = 0;
    while offset < characters.len() {
        let size = sizes.get(size_index).copied().unwrap_or(1).max(1);
        let end = (offset + size).min(characters.len());
        chunks.push(characters[offset..end].iter().collect());
        offset = end;
        size_index += 1;
    }
    chunks
}

fn main() {
    let mut args = std::env::args().skip(1);
    let parser_name = args.next().expect("parser");
    let mode = args.next().expect("mode");
    let wire = args.next().expect("wire");
    let tools = args
        .next()
        .filter(|encoded| !encoded.is_empty())
        .map(|encoded| serde_json::from_str::<Vec<Tool>>(&encoded).expect("tools JSON"))
        .unwrap_or_else(default_tools);
    let chunk_sizes = args
        .next()
        .map(|encoded| serde_json::from_str::<Vec<usize>>(&encoded).expect("chunk sizes JSON"))
        .unwrap_or_default();
    let mut parser = parser(&parser_name, &tools);
    let mut output = ToolParserOutput::default();

    let parse_result = if mode == "stream" {
        let mut result = Ok(());
        for chunk in stream_chunks(&wire, &chunk_sizes) {
            let mut delta = ToolParserOutput::default();
            if let Err(error) = parser.parse_into(&chunk, &mut delta) {
                result = Err(error);
                break;
            }
            output.append(delta);
        }
        result
    } else {
        parser.parse_into(&wire, &mut output)
    };

    if let Err(error) = parse_result {
        println!("{}", json!({"parser": parser_name, "error": error.to_string()}));
        return;
    }
    match parser.finish() {
        Ok(tail) => output.append(tail),
        Err(error) => {
            println!("{}", json!({"parser": parser_name, "error": error.to_string()}));
            return;
        }
    }
    let output = output.coalesce_calls();
    let calls = output
        .calls
        .into_iter()
        .map(|call| {
            let arguments: Value = serde_json::from_str(&call.arguments).unwrap();
            json!({
                "index": call.tool_index,
                "name": call.name,
                "arguments": arguments
            })
        })
        .collect::<Vec<_>>();
    println!(
        "{}",
        json!({
            "parser": parser_name,
            "normal_text": output.normal_text,
            "calls": calls
        })
    );
}
