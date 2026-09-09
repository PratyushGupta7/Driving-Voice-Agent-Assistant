from __future__ import annotations

import json
from pathlib import Path

import aiosqlite

from .models import FenceDecision, MissionSnapshot, OperationResult, OutputGate


SCHEMA = """
CREATE TABLE IF NOT EXISTS missions (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    current_version INTEGER NOT NULL,
    current_output_epoch INTEGER NOT NULL,
    output_gate TEXT NOT NULL,
    status TEXT NOT NULL,
    constraints_json TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS mission_versions (
    mission_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    constraints_json TEXT,
    source_turn_text TEXT,
    source_input_sequence INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (mission_id, version)
);
CREATE TABLE IF NOT EXISTS operations (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    mission_id TEXT NOT NULL,
    mission_version INTEGER NOT NULL,
    output_epoch INTEGER NOT NULL,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT
);
CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id TEXT NOT NULL,
    normalized_result_json TEXT,
    provider TEXT,
    fence_decision TEXT NOT NULL,
    rejection_reason TEXT,
    received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


class Repository:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    async def init(self) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(SCHEMA)
            await db.commit()

    async def persist_snapshot(
        self,
        snap: MissionSnapshot,
        source_turn: str = "",
        *,
        write_version: bool = True,
        input_sequence: int = 0,
    ) -> None:
        if not snap.mission_id:
            return
        async with aiosqlite.connect(self.path) as db:
            await db.execute("BEGIN IMMEDIATE")
            await db.execute(
                """
                INSERT INTO missions (id, session_id, current_version, current_output_epoch,
                    output_gate, status, constraints_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    current_version=excluded.current_version,
                    current_output_epoch=excluded.current_output_epoch,
                    output_gate=excluded.output_gate,
                    status=excluded.status,
                    constraints_json=excluded.constraints_json,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    snap.mission_id,
                    snap.session_id,
                    snap.mission_version,
                    snap.output_epoch,
                    snap.output_gate.value,
                    snap.status,
                    snap.constraints.model_dump_json() if snap.constraints else None,
                ),
            )
            if write_version and snap.mission_version > 0:
                await db.execute(
                    """
                    INSERT OR IGNORE INTO mission_versions
                    (mission_id, version, constraints_json, source_turn_text, source_input_sequence)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        snap.mission_id,
                        snap.mission_version,
                        snap.constraints.model_dump_json() if snap.constraints else None,
                        source_turn,
                        input_sequence,
                    ),
                )
            await db.commit()

    async def record_operation(self, result: OperationResult, status: str) -> None:
        token = result.token
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO operations
                (id, session_id, mission_id, mission_version, output_epoch, kind, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.operation_id,
                    token.session_id,
                    token.mission_id,
                    token.mission_version,
                    token.output_epoch,
                    token.request_kind,
                    status,
                ),
            )
            await db.commit()

    async def attach_result_if_head_matches(
        self,
        result: OperationResult,
        expected: MissionSnapshot,
    ) -> bool:
        """Accept when the live actor still matches the token. DB cannot veto that."""
        token = result.token
        matches = (
            bool(expected.mission_id)
            and expected.mission_id == token.mission_id
            and expected.session_id == token.session_id
            and expected.mission_version == token.mission_version
            and expected.output_epoch == token.output_epoch
            and expected.output_gate == OutputGate.OPEN
            and expected.latest_request_id.get(token.request_kind) == token.request_id
        )
        async with aiosqlite.connect(self.path) as db:
            await db.execute("BEGIN IMMEDIATE")
            if matches:
                await db.execute(
                    """
                    INSERT INTO missions (id, session_id, current_version, current_output_epoch,
                        output_gate, status, constraints_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        current_version=excluded.current_version,
                        current_output_epoch=excluded.current_output_epoch,
                        output_gate=excluded.output_gate,
                        status=excluded.status,
                        constraints_json=excluded.constraints_json,
                        updated_at=CURRENT_TIMESTAMP
                    """,
                    (
                        expected.mission_id,
                        expected.session_id,
                        expected.mission_version,
                        expected.output_epoch,
                        expected.output_gate.value,
                        expected.status,
                        expected.constraints.model_dump_json() if expected.constraints else None,
                    ),
                )
            decision = FenceDecision.ACCEPTED if matches else FenceDecision.STALE_REJECTED
            reason = None if matches else "actor_head_mismatch"
            await db.execute(
                """
                INSERT INTO results (operation_id, normalized_result_json, provider, fence_decision, rejection_reason)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    result.operation_id,
                    result.model_dump_json(),
                    result.provider,
                    decision.value,
                    reason,
                ),
            )
            await db.execute(
                """
                INSERT OR REPLACE INTO operations
                (id, session_id, mission_id, mission_version, output_epoch, kind, status, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    result.operation_id,
                    token.session_id,
                    token.mission_id,
                    token.mission_version,
                    token.output_epoch,
                    token.request_kind,
                    "accepted" if matches else "stale_rejected",
                ),
            )
            await db.commit()
            return matches

    async def note_emission_rejected(self, operation_id: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO results (operation_id, normalized_result_json, provider, fence_decision, rejection_reason)
                VALUES (?, ?, ?, ?, ?)
                """,
                (operation_id, "{}", "runtime", FenceDecision.STALE_REJECTED.value, "emit_after_cas_failed"),
            )
            await db.execute(
                "UPDATE operations SET status = 'stale_rejected', completed_at = CURRENT_TIMESTAMP WHERE id = ?",
                (operation_id,),
            )
            await db.commit()
