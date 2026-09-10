import asyncio
import json

from backend.server import server_utils


def test_feedback_is_delivered_while_task_is_running(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    async def exercise():
        incoming = asyncio.Queue()
        requested, received = asyncio.Event(), asyncio.Event()
        answers = []

        class Socket:
            async def receive_text(self):
                return await incoming.get()

            async def send_json(self, data):
                if data.get("type") == "human_feedback":
                    requested.set()

            async def send_text(self, text):
                pass

        async def start(socket, data, manager, feedback_queue):
            handler = server_utils.CustomLogsHandler(socket, "review", feedback_queue)
            feedback_queue.handler = handler
            answers.append(await handler.request_feedback("确认计划"))
            received.set()

        monkeypatch.setattr(server_utils, "handle_start_command", start)
        loop = asyncio.create_task(server_utils.handle_websocket_communication(Socket(), None))
        await incoming.put('start {}')
        await asyncio.wait_for(requested.wait(), 1)
        await incoming.put(json.dumps({"type": "human_feedback", "content": "增加基线"}))
        await asyncio.wait_for(received.wait(), 1)
        assert answers == ["增加基线"]
        loop.cancel()
        try:
            await loop
        except asyncio.CancelledError:
            pass

    asyncio.run(exercise())
