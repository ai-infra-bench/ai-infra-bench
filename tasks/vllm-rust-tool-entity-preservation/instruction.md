We use the Rust frontend with XML-style tool calls for file-writing and search tools. Requests succeed and the tool name is correct, but literal entity text in string arguments is changed before it reaches the tool. For example, a write_file content value of Tom &amp; Jerry &lt;3 is returned as Tom & Jerry <3.

The same mismatch appears in four parser formats:

| Parser | Raw value emitted by the model | Current parsed value |
| --- | --- | --- |
| minimax_m2 | Tom &amp; Jerry &lt;3 | Tom & Jerry <3 |
| qwen_coder | 杭州 &lt;/parameter&gt;... | 杭州 </parameter>... |
| glm_xml | Paris &lt;/arg_value&gt;... | Paris </arg_value>... |
| deepseek_dsml | Hangzhou &lt;/｜DSML｜parameter&gt;... | Hangzhou </｜DSML｜parameter>... |

Preserve string parameter values byte-for-byte in complete and streaming parsing for all four formats. Numeric, boolean, object, array, and null parameters must keep their existing schema conversion; normal assistant text, multiple tool calls, incomplete-stream handling, and tool-call ordering must not regress. This task does not ask the parser to reinterpret a raw </parameter> delimiter inside a value: that delimiter is inherently ambiguous in these protocols, while escaped delimiter text must remain escaped.
