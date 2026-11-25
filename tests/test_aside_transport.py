"""Protocol simulations only; these tests never count as actual model execution."""
from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path
import re
import sys
import tempfile
import time
import unittest
from unittest.mock import AsyncMock

SKILL = Path(__file__).resolve().parents[1] / "skills/remorsearch-ux-qa"
sys.path.insert(0, str(SKILL))
from uxpersonas.aside_cli import AsideCli, AsideError, response_from_output, ssh_argv
from uxpersonas.aside_chatgpt import (AsideChatHost, OwnedProChat, decode_assistant,
                                    prompt_for, pro_selected, ref, stable_conversation)
from uxpersonas.agent_run import Limits
from uxresearch.canonical import EngineError
from uxresearch.storage import read_json

PROFILE = "u0:11111111-1111-4111-8111-111111111111"
URL = "https://chatgpt.com/c/11111111-1111-4111-8111-111111111111?temporary-chat=true"
TREE = ('- button "ChatGPT 모델 선택" [ref=e1]: "Pro"\n'
        '- textbox "ChatGPT에게 물어보세요" [ref=e2]\n'
        '- button "보내기" [ref=e3] [disabled]')
READY_TREE = TREE.replace(" [disabled]", "")


def request(operation="op-a", context="ctx-a"):
    return dict(operation_id=operation, context_id=context, request_sha256="c" * 64,
                deadline=time.time() + 100, binding={"persona": context},
                payload={"task": {"success_criteria": ["retention"], "recovery_criteria": ["save"]},
                         "observations": []})


class ProtocolTests(unittest.TestCase):
    def test_ssh_uses_exact_reviewed_alias_and_strict_noninteractive_route(self):
        args = ssh_argv("approved-alias", PROFILE)
        self.assertEqual(args[:7], ["ssh", "-tt", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "approved-alias"])
        self.assertIn("--host local repl", args[-1])
        for alias in ["-F", "x;id", "x y", "x$(id)", "../x"]:
            with self.assertRaises(AsideError):
                ssh_argv(alias, PROFILE)
        with self.assertRaises(AsideError):
            ssh_argv("approved-alias", PROFILE, "exec")
        with self.assertRaises(AsideError):
            ssh_argv("approved-alias", "u0:$(secret)")

    def test_pty_echo_is_not_a_response(self):
        marker = "REMORSEARCH_ASIDE_test:"
        echo = ('repl > console.log("' + marker + '"+...)').encode()
        with self.assertRaises(AsideError):
            response_from_output(echo, marker)
        response = marker + '{"ok":true,"value":{"ready":true}}\r\n'
        self.assertEqual(response_from_output(echo + b"\r\n" + response.encode(), marker), {"ready": True})

    def test_duplicate_and_error_envelopes_are_rejected(self):
        marker = "M:"
        for raw in [b'M:{"ok":true,"value":1}\nM:{"ok":true,"value":1}',
                    b'M:{"ok":1,"value":1}', b'M:{"ok":false,"value":"stopped"}']:
            with self.assertRaises(AsideError):
                response_from_output(raw, marker)

    def test_observed_controls_require_one_enabled_match(self):
        self.assertEqual(ref(READY_TREE, "button", "보내기"), "e3")
        for tree in [TREE, READY_TREE + '\n- button "보내기" [ref=e4]', "- button Send [ref=e3]"]:
            with self.assertRaises(AsideError):
                ref(tree, "button", "보내기")
        self.assertTrue(pro_selected(TREE))
        self.assertFalse(pro_selected(TREE.replace('"Pro"', '"Instant"')))

    def test_only_stable_owned_temporary_conversation_is_admitted(self):
        self.assertEqual(stable_conversation(URL), URL)
        for url in [URL.replace("true", "false"), URL.replace("chatgpt.com", "chatgpt.com.evil"),
                    "https://chatgpt.com/", "https://chatgpt.com/c/local-chatgpt%3A123?temporary-chat=true"]:
            with self.assertRaises(AsideError):
                stable_conversation(url)

    def test_assistant_role_and_operation_are_required(self):
        text = 'ChatGPT 답변:\n\n{"response_to":"op-a","result":{"kind":"tool"}}'
        self.assertEqual(decode_assistant(text, "op-a"), {"kind": "tool"})
        for bad in [text.replace("ChatGPT 답변", "내가 한 말"), text.replace("op-a", "op-old"),
                    text + "\ntrailing", text.replace('"result":{', '"extra":1,"result":{')]:
            with self.assertRaises((AsideError, ValueError)):
                decode_assistant(bad, "op-a")

    def test_prompt_keeps_own_observations_without_mutating_input(self):
        req = request()
        req["payload"]["observations"] = [{"id": "obs-1", "captures": [{"path": "/private/owned.png", "sha256": "a" * 64}]}]
        before = copy.deepcopy(req)
        prompt = prompt_for("model", req)
        self.assertEqual(req, before)
        self.assertIn('"response_to":"op-a"', prompt)
        self.assertIn("obs-1", prompt)
        self.assertNotIn("/private/owned.png", prompt)
        self.assertNotIn("\n", prompt)

    def test_extended_deadlines_are_explicit_and_bounded(self):
        self.assertEqual(Limits().close_seconds, 2)
        Limits(call_seconds=180, task_seconds=1500, close_seconds=15).validate()
        for limits in [Limits(call_seconds=181), Limits(task_seconds=1801), Limits(close_seconds=16)]:
            with self.assertRaises(EngineError):
                limits.validate()


class FakeInput:
    def __init__(self, cli):
        self.cli, self.writes = cli, []
    def write(self, value):
        state = read_json(self.cli.journal / "state.json", private=True)["payload"]
        if value != b"exit\n":
            assert state["operations"][-1]["status"] == "intent"
        self.writes.append(value)
    async def drain(self):
        pass


class CliTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.cli = AsideCli(alias="approved-alias", profile=PROFILE, journal=self.root / "cli")
        self.input = FakeInput(self.cli)
        self.cli.process = type("Process", (), {"returncode": None, "stdin": self.input})()
    def tearDown(self):
        self.temp.cleanup()

    async def test_durable_intent_and_correlated_completion(self):
        async def reply(timeout):
            script = self.input.writes[-1]
            marker = re.search(rb"REMORSEARCH_ASIDE_[a-f0-9]+:", script)[0]
            return script + marker + b'{"ok":true,"value":{"ready":true}}\nrepl > '
        self.cli._until_prompt = reply
        self.assertEqual(await self.cli.rpc("return {ready:true};", label="sample"), {"ready": True})
        state = read_json(self.cli.journal / "state.json", private=True)["payload"]
        self.assertEqual(state["operations"][0]["status"], "done")
        self.assertFalse(state["uncertain"])

    async def test_eof_quarantines_context_without_resending(self):
        self.cli._until_prompt = AsyncMock(side_effect=AsideError("EOF"))
        with self.assertRaises(AsideError):
            await self.cli.rpc("return true;", label="first")
        with self.assertRaises(AsideError):
            await self.cli.rpc("return true;", label="second")
        self.assertEqual(len(self.input.writes), 1)
        self.assertTrue(self.cli.uncertain)

    async def test_cancellation_preserves_uncertain_intent(self):
        self.cli._until_prompt = AsyncMock(side_effect=asyncio.CancelledError())
        with self.assertRaises(asyncio.CancelledError):
            await self.cli.rpc("return true;", label="cancelled")
        self.assertTrue(self.cli.uncertain)
        self.assertEqual(self.cli.records[-1]["status"], "uncertain")

    async def test_existing_journal_cannot_restart(self):
        with self.assertRaises(AsideError):
            AsideCli(alias="approved-alias", profile=PROFILE, journal=self.root / "cli")

    async def test_owned_page_can_only_be_opened_once(self):
        self.cli.rpc = AsyncMock(return_value={"ownedTabs": 1, "url": "https://chatgpt.com/", "tree": TREE})
        await self.cli.open_owned()
        with self.assertRaises(AsideError):
            await self.cli.open_owned()
        self.assertEqual(self.cli.rpc.await_count, 1)

    async def test_confirmed_page_removal_and_process_exit_are_not_repeated(self):
        self.cli.owned, self.cli.page_closed = True, True
        self.cli.process.returncode = 0
        self.cli.rpc = AsyncMock()
        self.assertEqual(await self.cli.close_owned(model_quiescent=True), {"stopped": True})
        self.cli.rpc.assert_not_awaited()
        state = read_json(self.cli.journal / "state.json", private=True)["payload"]
        self.assertTrue(state["page_closed"])
        self.assertEqual(state["process_returncode"], 0)


class ChatTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.cli = AsideCli(alias="approved-alias", profile=PROFILE, journal=self.root / "cli")
        self.cli.owned, self.cli.remote_session_id = True, "owned-test"
        self.chat = OwnedProChat(self.cli, evidence=self.root / "chat")
        self.chat.ready, self.chat.url = True, URL
        self.sent, self.staged = 0, ""
        self.readiness_tree = READY_TREE
        self.req = request()
        self.old = {"message_ids": "old", "text": "old", "key": "assistant"}
        self.new = {"message_ids": "new", "key": "assistant",
                    "text": 'ChatGPT 답변:\n\n{"response_to":"op-a","result":{"kind":"tool","tool":"inspect","arguments":{},"decision":"Observe my own state."}}'}
        self.chat.view = AsyncMock(side_effect=lambda: self.view())
        self.cli.rpc = AsyncMock(side_effect=self.rpc)

    def tearDown(self):
        self.temp.cleanup()

    def view(self):
        return {"url": URL, "tree": TREE, "answers": [self.old] + ([self.new] if self.sent else [])}

    async def rpc(self, body, *, label, **kwargs):
        if label == "owned-empty-composer":
            return ""
        if label == "owned-prompt-stage":
            self.staged = ""
        if label == "owned-prompt-chunk":
            self.staged += json.JSONDecoder().raw_decode(body.split("+=", 1)[1])[0]
        if label == "owned-prompt-length":
            return len(self.staged.encode("utf-16-le")) // 2
        if label == "owned-final-prompt-check":
            return self.staged
        if label == "owned-send-readiness":
            return {"tree": self.readiness_tree}
        if label == "owned-fill-reviewed-prompt":
            return {"same": True, "actual": self.staged, "tree": READY_TREE}
        if label.startswith("owned-send-"):
            self.sent += 1
        return True

    async def test_model_completion_is_idempotent_without_second_send(self):
        first = await self.chat.reply("model", self.req)
        second = await self.chat.reply("model", self.req)
        self.assertEqual(first, second)
        self.assertEqual(self.sent, 1)
        self.assertFalse(self.chat.pending)
        record = read_json(self.chat.evidence / "op-a.json", private=True)
        self.assertEqual(record["message_ids"], "new")
        self.assertEqual(record["status"], "done")

    async def test_probe_is_separate_and_idempotent(self):
        self.chat.probe_request = request("probe-a")
        self.new["text"] = 'ChatGPT 답변:\n\n{"response_to":"probe-a","result":{"ready":true}}'
        self.assertEqual(await self.chat.transport_probe(), {"ready": True})
        self.assertEqual(await self.chat.transport_probe(), {"ready": True})
        self.assertEqual(self.sent, 1)
        self.assertEqual([x[2] for x in self.chat.model_intervals], ["probe"])

    async def test_review_preserves_response_without_provider_screenshot(self):
        self.new["text"] = ('ChatGPT 답변:\n\n' + json.dumps({"response_to": "op-a", "result": {
            "reason": "Own recorded evidence only", "criteria": []}}))
        result = await self.chat.reply("review", self.req)
        self.assertEqual(result["reason"], "Own recorded evidence only")
        record = read_json(self.chat.evidence / "op-a.json", private=True)
        self.assertEqual(record["response_text"], self.new["text"])
        self.assertNotIn("capture", record)
        self.assertFalse(list(self.chat.evidence.glob("*.png")))
        self.assertFalse(any("screenshot" in c.args[0] for c in self.cli.rpc.call_args_list))
        self.assertEqual(self.sent, 1)

    async def test_changed_request_cannot_reuse_completed_operation(self):
        await self.chat.reply("model", self.req)
        changed = copy.deepcopy(self.req)
        changed["payload"]["task"]["success_criteria"] = ["changed"]
        with self.assertRaises(AsideError):
            await self.chat.reply("model", changed)
        self.assertEqual(self.sent, 1)

    async def test_stale_assistant_is_not_accepted_or_resent(self):
        self.new["text"] = self.new["text"].replace("op-a", "op-stale")
        self.req["deadline"] = time.time() + 2.5
        with self.assertRaises(AsideError):
            await self.chat.reply("model", self.req)
        with self.assertRaises(AsideError):
            await self.chat.reply("model", self.req)
        self.assertEqual(self.sent, 1)
        self.assertTrue(self.chat.pending)

    async def test_remounted_old_reply_is_ignored_until_correlated_reply(self):
        count = 0
        def observed():
            nonlocal count
            state = self.view()
            if self.sent:
                count += 1
                if count == 1:
                    state["answers"] = [dict(self.old, message_ids="remounted-old")]
            return state
        self.chat.view = AsyncMock(side_effect=observed)
        result = await self.chat.reply("model", self.req)
        self.assertEqual(result["tool"], "inspect")
        self.assertEqual(self.sent, 1)
        self.assertFalse(self.chat.pending)

    async def test_incomplete_json_waits_without_resending(self):
        count = 0
        def observed():
            nonlocal count
            state = self.view()
            if self.sent:
                count += 1
                if count == 1:
                    state["answers"][-1] = dict(self.new, text=self.new["text"][:-5])
            return state
        self.chat.view = AsyncMock(side_effect=observed)
        result = await self.chat.reply("model", self.req)
        self.assertEqual(result["tool"], "inspect")
        self.assertEqual(self.sent, 1)

    async def test_unsent_draft_blocks_all_send(self):
        self.cli.rpc = AsyncMock(return_value="unsent draft")
        with self.assertRaises(AsideError):
            await self.chat.reply("model", self.req)
        self.assertEqual(self.sent, 0)

    async def test_send_cancellation_does_not_prove_worker_stop(self):
        original = self.rpc
        async def cancelled(body, *, label, **kwargs):
            if label.startswith("owned-send-"):
                self.sent += 1
                raise asyncio.CancelledError()
            return await original(body, label=label, **kwargs)
        self.cli.rpc = AsyncMock(side_effect=cancelled)
        with self.assertRaises(asyncio.CancelledError):
            await self.chat.reply("model", self.req)
        self.cli.close_owned = AsyncMock(return_value={"stopped": False})
        self.assertEqual(await self.chat.close(), {"stopped": False})
        self.cli.close_owned.assert_awaited_once_with(model_quiescent=False)
        with self.assertRaises(AsideError):
            await self.chat.reply("model", self.req)
        self.assertEqual(self.sent, 1)

    async def test_disabled_send_waits_for_observed_ready_without_mutation(self):
        self.staged = "Owned prompt"
        self.chat.view = AsyncMock(return_value={"tree": READY_TREE})
        control, states = await self.chat.send_control(TREE, self.staged, time.time() + 5)
        self.assertEqual(control, "e3")
        self.assertEqual([s["disabled"] for s in states], [True, False])
        self.assertEqual(self.sent, 0)

    async def test_disabled_send_exhaustion_never_clicks(self):
        self.readiness_tree = TREE
        with self.assertRaisesRegex(AsideError, "remained disabled"):
            await self.chat.send_control(TREE, "Owned prompt", time.time() + 10)
        self.assertEqual(self.sent, 0)

    async def test_changed_owned_prompt_after_fill_never_sends(self):
        self.staged = "unexpected"
        with self.assertRaisesRegex(AsideError, "prompt changed"):
            await self.chat.send_control(READY_TREE, "expected", time.time() + 5)
        self.assertEqual(self.sent, 0)

    async def test_pre_send_dom_error_does_not_imply_model_generation(self):
        self.cli.uncertain = True
        self.chat.pending = False
        self.cli.close_owned = AsyncMock(return_value={"stopped": True})
        self.assertEqual(await self.chat.close(), {"stopped": True})
        self.cli.close_owned.assert_awaited_once_with(model_quiescent=True)

    async def test_already_nonpersonal_temporary_chat_is_not_toggled(self):
        start = TREE + '\n- button "임시 채팅" [ref=e4]'
        state = {"url": "https://chatgpt.com/?temporary-chat=true",
                 "tree": TREE + '\n- button "개인화되지 않음" [ref=e5]\n'
                         '- text: "이 채팅은 메모리, 플러그인, 사용자 지정 지침을 무시하며 기록에는 표시되지 않습니다"'}
        self.chat.view = AsyncMock(return_value={"url": "https://chatgpt.com/", "tree": start, "answers": []})
        self.chat._empty_composer = AsyncMock(return_value="e2")
        self.chat.click = AsyncMock(return_value=state)
        self.cli.rpc = AsyncMock(return_value=state)
        await self.chat.initialize()
        self.assertEqual(self.chat.click.await_count, 1)
        self.assertTrue(self.chat.ready)

    async def test_owned_empty_temporary_page_is_not_toggled_back(self):
        state = {"url": "https://chatgpt.com/?temporary-chat=true", "answers": [],
                 "tree": TREE + '\n- button "개인화되지 않음" [ref=e5]\n'
                         '- text: "이 채팅은 메모리, 플러그인, 사용자 지정 지침을 무시하며 기록에는 표시되지 않습니다"'}
        self.chat.view = AsyncMock(return_value=state)
        self.chat._empty_composer = AsyncMock(return_value="e2")
        self.chat.click = AsyncMock()
        self.cli.rpc = AsyncMock(return_value=state)
        await self.chat.initialize()
        self.chat.click.assert_not_awaited()
        self.assertTrue(self.chat.ready)

    async def test_wrong_model_preflight_never_switches_or_sends(self):
        state = {"url": "https://chatgpt.com/", "answers": [],
                 "tree": TREE.replace('"Pro"', '"Instant"')}
        self.chat.view = AsyncMock(return_value=state)
        self.chat.click = AsyncMock()
        with self.assertRaisesRegex(AsideError, "no model is selected automatically"):
            await self.chat.initialize()
        self.chat.click.assert_not_awaited()
        self.assertEqual(self.sent, 0)

    async def test_loading_preflight_is_read_only_until_ready(self):
        loading = {"url": "https://chatgpt.com/", "answers": [],
                   "tree": '- textbox "ChatGPT에게 물어보세요" [ref=e1]\n- button "임시 채팅" [ref=e2] [disabled]'}
        ready = {"url": "https://chatgpt.com/?temporary-chat=true", "answers": [],
                 "tree": TREE + '\n- button "개인화되지 않음" [ref=e5]\n'
                         '- text: "이 채팅은 메모리, 플러그인, 사용자 지정 지침을 무시하며 기록에는 표시되지 않습니다"'}
        self.chat.view = AsyncMock(side_effect=[loading, ready])
        self.chat._empty_composer = AsyncMock(return_value="e2")
        self.chat.click = AsyncMock()
        self.cli.rpc = AsyncMock(return_value=ready)
        await self.chat.initialize()
        self.assertEqual(self.chat.view.await_count, 2)
        self.chat.click.assert_not_awaited()
        self.assertEqual(self.sent, 0)


class HostTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.chats = []
        for i in range(2):
            cli = type("Cli", (), {"remote_session_id": "owned-" + str(i)})()
            chat = type("Chat", (), {})()
            chat.cli, chat.url = cli, URL + str(i)
            chat.reply = AsyncMock(return_value={"kind": "tool"})
            chat.close = AsyncMock(return_value={"stopped": True})
            self.chats.append(chat)
        self.tool = AsyncMock(return_value={"observed": True})
        self.close = AsyncMock(return_value={"stopped": True})
        self.host = AsideChatHost(self.chats, tool_call=self.tool, tool_close=self.close,
                                  evidence=self.root / "host", adapter_sha256="a" * 64)
    def tearDown(self):
        self.temp.cleanup()

    async def test_parallel_callbacks_use_distinct_contexts(self):
        a, b = request("op-a", "ctx-a"), request("op-b", "ctx-b")
        await asyncio.gather(self.host.respond("model", a), self.host.respond("model", b))
        self.assertIsNot(self.host.bound["ctx-a"], self.host.bound["ctx-b"])
        self.chats[0].reply.assert_awaited_once()
        self.chats[1].reply.assert_awaited_once()
        self.assertNotEqual(self.chats[0].reply.call_args.args[1]["context_id"],
                            self.chats[1].reply.call_args.args[1]["context_id"])

    async def test_partial_tool_failure_is_not_replayed(self):
        self.tool.side_effect = RuntimeError("uncertain tool effect")
        req = request()
        with self.assertRaises(RuntimeError):
            await self.host.respond("tool", req)
        with self.assertRaises(AsideError):
            await self.host.respond("tool", req)
        self.assertEqual(self.tool.await_count, 1)
        self.assertEqual(self.host.events[0]["status"], "uncertain")

    async def test_completed_tool_is_not_applied_twice(self):
        req = request()
        self.assertEqual(await self.host.respond("tool", req), await self.host.respond("tool", req))
        self.assertEqual(self.tool.await_count, 1)

    async def test_binding_change_cannot_dispatch(self):
        req = request()
        await self.host.respond("model", req)
        changed = request("op-next")
        changed["binding"]["persona"] = "changed"
        with self.assertRaises(AsideError):
            await self.host.respond("model", changed)
        self.assertEqual(self.chats[0].reply.await_count, 1)

    async def test_partial_cleanup_does_not_claim_stopped(self):
        self.chats[0].close.return_value = {"stopped": False}
        reply = await self.host.respond("close", request())
        self.assertEqual(reply["result"], {"stopped": False})

    async def test_third_context_cannot_reuse_a_page(self):
        await self.host.respond("model", request("op-a", "ctx-a"))
        await self.host.respond("model", request("op-b", "ctx-b"))
        with self.assertRaises(AsideError):
            await self.host.respond("model", request("op-c", "ctx-c"))


if __name__ == "__main__":
    unittest.main()
