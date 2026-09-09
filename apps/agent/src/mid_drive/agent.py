from __future__ import annotations

from livekit.agents import Agent, StopResponse
from livekit.agents.llm import ChatContext, ChatMessage

from .controller import MissionController

INSTRUCTIONS = """
You are a silent LiveKit session stub for Mid-Drive.
Do not answer the driver. Do not name shops, times, or parking.
The mission controller owns every spoken turn.
""".strip()


class MissionAgent(Agent):
    def __init__(self, controller: MissionController) -> None:
        super().__init__(instructions=INSTRUCTIONS)
        self._controller = controller

    async def on_user_turn_completed(
        self,
        turn_ctx: ChatContext,
        new_message: ChatMessage,
    ) -> None:
        text = (new_message.text_content or "").strip()
        if not text:
            await self._controller.on_empty_turn()
            raise StopResponse()
        await self._controller.commit_heard(text, "agent_turn")
        raise StopResponse()
