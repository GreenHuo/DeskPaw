"""Knowledge contracts and integration into chat and tool requests."""

import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from deskpaw.config import MCPServerConfig, Settings
from deskpaw.knowledge import KnowledgeChunk, KnowledgeService
from deskpaw.pet.window import PetWindow
from deskpaw.services.agent import run_excel_agent, run_tool_agent
from deskpaw.services.ai import ChatResponse, chat_response
from deskpaw.services.prompts import conversation_messages
from deskpaw.ui.worker import ChatWorker


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.hit = KnowledgeChunk(
            "chunk-1", "请假需要提前一天申请。", "handbook.md#leave", "员工手册"
        )
        self.retriever = Mock()
        self.retriever.retrieve.return_value = [self.hit]
        self.service = KnowledgeService(self.retriever, collection_ids=("company",))
        self.history = [{"role": "user", "content": "怎么请假？"}]

    def test_default_and_empty_queries_do_not_retrieve(self):
        self.assertFalse(KnowledgeService().context_for("hello").chunks)
        self.assertFalse(self.service.context_for("  ").chunks)
        self.retriever.retrieve.assert_not_called()

    def test_scoped_query_sources_deduplication_and_serialized_budget(self):
        self.retriever.retrieve.return_value = [
            self.hit,
            self.hit,
            KnowledgeChunk("chunk-2", '长内容"\n' * 500, "guide.md", "指南"),
        ]
        service = KnowledgeService(
            self.retriever, max_context_chars=400, collection_ids=("company",)
        )
        context = service.context_for("  怎么请假？  ")
        query = self.retriever.retrieve.call_args.args[0]
        self.assertEqual(
            (query.text, query.limit, query.collection_ids), ("怎么请假？", 4, ("company",))
        )
        self.assertEqual(len(context.chunks), 2)
        self.assertLessEqual(len(context.payload), 400)
        self.assertEqual(json.loads(context.payload)[0]["source"], self.hit.source)
        self.assertTrue(context.chunks[1].content)

    def test_result_limit_bounds_even_an_unbounded_backend(self):
        def hits():
            index = 0
            while True:
                yield KnowledgeChunk(str(index), "content", "source")
                index += 1

        self.retriever.retrieve.return_value = hits()
        self.assertEqual(
            len(KnowledgeService(self.retriever, limit=2).context_for("query").chunks), 2
        )

    def test_context_is_data_and_does_not_mutate_history(self):
        context = self.service.context_for("query")
        history = [{"role": "user", "content": str(index)} for index in range(20)]
        messages = conversation_messages("system", history, context)
        self.assertNotIn(self.hit.content, messages[0]["content"])
        self.assertEqual(messages[1]["role"], "user")
        self.assertIn(self.hit.source, messages[1]["content"])
        self.assertEqual(messages[2:], history[-12:])
        self.assertEqual(len(history), 20)
        self.assertEqual(
            conversation_messages("system", history),
            [{"role": "system", "content": "system"}, *history[-12:]],
        )

    def test_chat_and_both_agents_receive_the_same_context(self):
        context = self.service.context_for("query")
        settings = Settings(base_url="http://localhost:8080", pet_name="奶糖")
        with patch(
            "deskpaw.services.ai.completion_message", return_value={"content": "请提前申请。"}
        ) as model:
            chat_response(
                settings.base_url,
                settings.model,
                "",
                self.history,
                persona=settings.persona(),
                knowledge_context=context,
            )
            self.assertIn(self.hit.source, model.call_args.args[3][1]["content"])
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.xlsx"
            source.touch()
            settings.mcp_servers = [MCPServerConfig("documents", "unused")]
            for is_excel in (True, False):
                with (
                    self.subTest(is_excel=is_excel),
                    patch("deskpaw.services.agent.MCPClient") as client_type,
                    patch(
                        "deskpaw.services.agent.completion_message",
                        return_value={"content": "请提前申请。"},
                    ) as model,
                ):
                    client = client_type.return_value.__enter__.return_value
                    client.list_tools.return_value = [
                        {"name": "inspect", "inputSchema": {"type": "object"}}
                    ]
                    if is_excel:
                        run_excel_agent(
                            settings,
                            "",
                            self.history,
                            source,
                            lambda _: False,
                            knowledge_context=context,
                        )
                    else:
                        run_tool_agent(
                            settings,
                            "",
                            self.history,
                            None,
                            lambda _: False,
                            knowledge_context=context,
                        )
                    messages = model.call_args.args[3]
                    self.assertIn(self.hit.source, messages[1]["content"])
                    self.assertIn("奶糖", messages[0]["content"])
                    client.call_tool.assert_not_called()

    def test_tool_approval_still_applies_with_knowledge(self):
        settings = Settings(mcp_servers=[MCPServerConfig("documents", "unused")])
        answer = {
            "tool_calls": [{"id": "call-1", "function": {"name": "mcp_0_0", "arguments": "{}"}}]
        }
        with (
            patch("deskpaw.services.agent.MCPClient") as client_type,
            patch("deskpaw.services.agent.completion_message", return_value=answer),
        ):
            client = client_type.return_value.__enter__.return_value
            client.list_tools.return_value = [{"name": "write", "inputSchema": {"type": "object"}}]
            approve = Mock(return_value=False)
            result = run_tool_agent(
                settings,
                "",
                self.history,
                None,
                approve,
                knowledge_context=self.service.context_for("query"),
            )
            approve.assert_called_once()
            client.call_tool.assert_not_called()
            self.assertIn("已取消", result.reply)

    def test_worker_retrieves_on_background_thread_and_passes_context(self):
        app = QApplication.instance() or QApplication([])
        thread_ids = []

        def retrieve(query):
            thread_ids.append(threading.get_ident())
            return [self.hit]

        self.retriever.retrieve.side_effect = retrieve
        worker = ChatWorker(Settings(), "", self.history, knowledge=self.service)
        with patch("deskpaw.ui.worker.chat_response", return_value=ChatResponse("完成")) as chat:
            worker.start()
            self.assertTrue(worker.wait(3000))
            self.assertNotEqual(thread_ids, [threading.get_ident()])
            self.assertEqual(len(thread_ids), 1)
            self.assertEqual(chat.call_args.kwargs["knowledge_context"].chunks, (self.hit,))
        app.processEvents()

    def test_pet_passes_injected_service_to_chat(self):
        app = QApplication.instance() or QApplication([])
        pet = PetWindow(Settings(roam=False), knowledge=self.service)
        try:
            pet.open_chat()
            self.assertIs(pet.chat.knowledge, self.service)
        finally:
            pet.shutdown()
            pet.chat.close()
            pet.close()
            app.processEvents()
