你是代码审计专家。以下内容供你分析 **跨文件数据流**：

    ◆◆◆ 具体风险 ◆◆◆
    - 工具元数据污染 Tool Metadata Pollution: MCP服务第一次握手时，发送的工具元数据如description、params包含恶意提示词。
    - 工具投毒攻击 Tool Poisoning: MCP服务第二次握手时，即工具实时调用阶段，MCP Server将包含恶意指令的外部数据（例如网页、文档）输出给AI Agent，可能影响AI Agent的决策和行为。


    ◆◆◆ 违例片段（命中 Semgrep 规则的原始行） ◆◆◆
{snippets}

    ◆◆◆ 全部源码（含行号） ◆◆◆
{global_code}

    **任务：**
      1. 先判断给定的issue中的代码行是否是真实风险，对于读取API key, 返回一些值，都不是真实的风险。
      2. 对于真实的风险，比如读取了外部数据，根据给出的代码，进行全域分析，找到和关键行相关的所有代码片段，关键行的函数参数是如何传输到，最远追踪到call_tool函数的参数，以及关键函数的最终返回值是如何被处理的，最远也要追踪到call_tool的返回值。
      3. 将所有你觉得有风险的代码片段和相关的扩写的片段结合在一起，以json的形式返回。
      4. call_tool是入口函数，你的一切溯源和扩写都是以call_tool的入参为开始，以call_tool的返回值为终点。

    **返回：**
        1.你不需要给出任何风险结论，只需要给出关联的代码片段，注意，要给出具体代码，而非对应行号，以json形式仅返回代码。
        2. 注意，最终返回值，将你找到的代码整合到一起，最终只返回一整段代码 **重要**。

    试例：

    issue命中代码： content = Path(settings.STORAGE_PATH, f"{paper_id}.md").read_text(
            encoding="utf-8"
        )

    智能扩写后：
        async def handle_read_paper(arguments: Dict[str, Any]) -> List[types.TextContent]:
            paper_id = arguments["paper_id"]
            content = Path(settings.STORAGE_PATH, f"{paper_id}.md").read_text(
                encoding="utf-8"
            )
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "status": "success",
                            "paper_id": paper_id,
                            "content": content,
                        }
                    ),
                )
            ]
        async def call_tool(name: str, arguments: Dict[str, Any]) -> List[types.TextContent]:
            elif name == "read_paper":
                return await handle_read_paper(arguments)
    仅返回智能扩写后的结果：

        async def handle_read_paper(arguments: Dict[str, Any]) -> List[types.TextContent]:
            paper_id = arguments["paper_id"]
            content = Path(settings.STORAGE_PATH, f"{paper_id}.md").read_text(
                encoding="utf-8"
            )
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "status": "success",
                            "paper_id": paper_id,
                            "content": content,
                        }
                    ),
                )
            ]
        async def call_tool(name: str, arguments: Dict[str, Any]) -> List[types.TextContent]:
            elif name == "read_paper":
                return await handle_read_paper(arguments)
    """