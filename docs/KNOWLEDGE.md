# 知识库扩展预留

当前已实现可选检索接口及聊天接入点，默认不启用。尚未实现文档导入、切分、Embedding、向量索引、管理界面或具体检索后端；也没有自动扫描本地文件或上传文档。

## 已有接口

| 接口 | 职责 |
| --- | --- |
| `KnowledgeQuery` | 查询文本、返回条数、允许检索的集合 ID |
| `KnowledgeChunk` | 稳定片段 ID、正文、来源、资料标题 |
| `KnowledgeRetriever` | `retrieve(query)`，返回按相关性排序的片段 |
| `KnowledgeService` | 可选调用后端，去重，限制条数与序列化上下文长度 |
| `KnowledgeContext` | 实际送入模型的 JSON 数据及对应片段 |

默认最多 4 条、6,000 个字符的 JSON 上下文；可配置范围分别为 1–20 条和 256–32,000 字符。预算包含 JSON 转义和来源元数据，超长正文截断，放不下的片段不注入。标题、来源和 ID 也有长度上限。字符预算不是模型 token 预算，具体模型适配可在以后增加。

`collection_ids` 原样传入后端。后端必须执行集合过滤与权限检查；空元组的范围由后端明确约定，不能默认解释成所有用户的数据。后端同时负责超时、取消策略、线程安全和连接生命周期。

## 接入方式

实现 `KnowledgeRetriever` 并在应用入口注入即可，不必修改聊天或宠物绘制代码。以下是仅用于演示的内存后端：

```python
from deskpaw.__main__ import main
from deskpaw.knowledge import KnowledgeChunk, KnowledgeQuery, KnowledgeService


class HandbookRetriever:
    def retrieve(self, query: KnowledgeQuery) -> list[KnowledgeChunk]:
        if "handbook" not in query.collection_ids or "请假" not in query.text:
            return []
        return [
            KnowledgeChunk(
                chunk_id="leave-policy-1",
                content="请假需要提前一天申请。",
                source="handbook.md#leave",
                title="员工手册",
            )
        ][:query.limit]


if __name__ == "__main__":
    knowledge = KnowledgeService(
        HandbookRetriever(), collection_ids=("handbook",), limit=4,
        max_context_chars=6000,
    )
    raise SystemExit(main(knowledge=knowledge))
```

注入链路是 `main → PetWindow → ChatDialog → ChatWorker`。后台线程针对最近一条用户消息检索一次，将同一份上下文传给普通聊天或对应的 Agent。Agent 的后续工具轮次复用本次上下文。未注入后端、没有用户消息或检索为空时，仍使用原来的聊天消息结构。

也可以在无界面调用中先执行 `service.context_for(question)`，再将结果通过 `knowledge_context=` 传给 `chat_response`、`run_excel_agent` 或 `run_tool_agent`。

## 模型与权限边界

检索片段作为单独的参考数据消息传入，不拼接为系统指令。共享系统提示要求模型忽略资料内的命令、注明使用资料的标题或来源，并在依据不足时说明。来源由检索后端提供；当前没有独立的引用卡片、回答事实核验或引用真实性校验。

接入远程聊天模型后，选中的检索片段与来源会随请求发送给该模型。真正提供知识库管理功能时，需要让用户明确选择可检索资料和数据发送范围。检索不能绕过已有的工具确认逻辑；即使资料中包含“执行工具”的文字，外部工具仍须走确认流程。

检索异常当前由聊天工作线程报告为失败，不会悄悄把失败当作无结果。具体后端应设定有限超时；以后若加入降级回答，需要向用户明确说明本次未使用知识库。

## 后续实施顺序

1. 在 `integrations/knowledge/` 添加文档解析、切分和索引适配器，保留稳定的文档及片段 ID，并记录来源位置。
2. 实现 `KnowledgeRetriever`：集合过滤、权限、相关性排序、超时、索引版本与过期文档处理。
3. 为导入、更新、删除和索引任务单独定义应用服务；检索协议保持只读，不混入文件修改能力。
4. 增加知识库配置和界面：选择目录或文件、集合开关、索引进度、资料发送说明、引用展示。
5. 按实际需求接入本地全文检索、向量数据库或远程知识服务，并用权限隔离、检索质量和引用准确率测试验证。

当前回归测试覆盖默认关闭、集合传递、去重、结果与长度预算、后台线程调用、三条聊天路径共用上下文，以及知识上下文不会绕过工具确认。
