#!/usr/bin/env python3
"""Unit tests for scripts/lib/log_sources.py — the two transcript formats.

Run directly (`python3 -m unittest tests/unit_codex_logs.py`) or through
scripts/test.sh, which calls this file as one assertion group.

What is pinned here is everything that would fail SILENTLY — a mis-read log
does not crash, it produces a smaller number, and a smaller number reads
exactly like a quiet week:

  · **Double-counting.** Codex puts every user and assistant turn on the wire
    twice (`response_item`, then `event_msg` again). Reading both doubles every
    hit downstream and nothing complains.
  · **The prompt bundled with injected context.** Five Codex user messages in
    six arrive as [the human's prompt, <environment_context>] in ONE message.
    A filter that drops the message deletes the prompt with it, and the corpus
    just gets shorter.
  · **Sub-agent traffic read as the human's voice.** Codex writes a sub-agent
    its own file whose header's `source` is an OBJECT where a normal session
    has a string — the shape that crashes a reader written against user
    sessions only.
  · **Claude Code drift.** Everything about the older path has to keep
    behaving as it did, so the codex work cannot quietly cost a Claude user
    their history. Bare-string content, promptSource, isMeta, toolUseResult
    and sidechain flags are all asserted here.
  · **Physical line numbers.** correction_scan's event identity is
    session|line|ts|sha and it is PERSISTED. Counting only the lines that
    parse would renumber every record and re-fire every event already retired.

Fixtures are hand-written synthetic sessions under tests/fixtures/codex/ — no
real transcript is copied into this repo. Stdlib only.
"""
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "scripts", "lib"))

import log_sources  # noqa: E402
from log_sources import CLAUDE, CODEX  # noqa: E402
sys.path.insert(0, os.path.join(REPO, "scripts"))
import correction_scan  # noqa: E402

FIXTURES = os.path.join(HERE, "fixtures", "codex")
S1 = "00000000-0000-4000-8000-000000000001"
S2 = "00000000-0000-4000-8000-000000000002"
S3 = "00000000-0000-4000-8000-000000000003"

CLAUDE_LOG = [
    # a plain human turn, content as a BARE STRING (the older shape)
    {"type": "user", "timestamp": "2026-09-01T11:00:00.000Z",
     "promptSource": "typed", "message": {"role": "user", "content": "やめて"}},
    # an assistant turn, content as typed blocks, with a non-text block mixed in
    {"type": "assistant", "timestamp": "2026-09-01T11:00:01.000Z",
     "message": {"role": "assistant", "content": [
         {"type": "thinking", "thinking": "hidden"},
         {"type": "text", "text": "Understood."}]}},
    # tool output wearing the user role
    {"type": "user", "timestamp": "2026-09-01T11:00:02.000Z",
     "toolUseResult": {"stdout": "ok"},
     "message": {"role": "user", "content": [{"type": "tool_result",
                                              "content": "ok"}]}},
    # a sub-agent's prompt: the "user" here is another agent
    {"type": "user", "timestamp": "2026-09-01T11:00:03.000Z",
     "isSidechain": True, "promptSource": "typed",
     "message": {"role": "user", "content": "count them"}},
    # harness bookkeeping
    {"type": "user", "timestamp": "2026-09-01T11:00:04.000Z", "isMeta": True,
     "promptSource": "typed",
     "message": {"role": "user", "content": "<command-name>/clear</command-name>"}},
    # a turn the harness injected, not typed
    {"type": "user", "timestamp": "2026-09-01T11:00:05.000Z",
     "promptSource": "tool_injected",
     "message": {"role": "user", "content": "You have 3 unread messages"}},
    {"type": "summary", "summary": "not a turn at all"},
]


def write_claude_log(dirpath, session_id="11111111-2222-4333-8444-555555555555"):
    os.makedirs(dirpath, exist_ok=True)
    path = os.path.join(dirpath, session_id + ".jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        for o in CLAUDE_LOG:
            fh.write(json.dumps(o, ensure_ascii=False) + "\n")
    return path


class CodexNormalisation(unittest.TestCase):
    def setUp(self):
        self.src = log_sources.CodexSessionsSource([FIXTURES])
        self.files = {sf.session_id: sf for sf in self.src.iter_files()}

    def test_walks_the_date_partitioned_tree(self):
        # Codex nests sessions under YYYY/MM/DD; a flat glob finds nothing.
        self.assertEqual(sorted(self.files), [S1, S2, S3])

    def test_identity_is_the_file_not_the_root_thread(self):
        # A sub-agent's header carries the PARENT in `session_id` and itself in
        # `id`. Keying on `session_id` would give two sub-agents of one parent
        # the same identity — and correction_scan dedups on it.
        self.assertEqual(self.files[S2].parent_id, S1)
        self.assertEqual(self.files[S2].session_id, S2)

    def test_header_carries_cwd(self):
        self.assertEqual(self.files[S1].cwd, "/home/example/demo")

    def test_subagent_object_source_is_a_sidechain(self):
        # `source` is a string on a user session and an OBJECT here. Reading it
        # as a string is the crash; missing the flag is the silent bug.
        self.assertTrue(self.files[S2].is_sidechain)
        self.assertFalse(self.files[S1].is_sidechain)
        for rec in self.files[S2].records():
            self.assertTrue(rec["is_sidechain"])

    def test_a_session_another_agent_opened_is_a_sidechain(self):
        # 実測: このマシンの ~/.codex/sessions には originator="Claude Code" の
        # 行が53件あった——Claude Code が codex を呼んだセッションで、その
        # "user" 発話を書いたのは人間ではなく別のエージェント。
        # thread_source は "user"・parent_thread_id も無い（＝既存の3つの手掛か
        # りはどれも立たない）ので、originator を見ないと**あなたの訂正として
        # 採取される**。蒸留が学ぶ相手が人間でなくなるのが、この行の防ぐ失敗。
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        day = os.path.join(tmp, "2026", "09", "02")
        os.makedirs(day)
        sid = "00000000-0000-4000-8000-0000000000aa"
        path = os.path.join(day, "rollout-2026-09-02T10-00-00-" + sid + ".jsonl")
        with open(path, "w") as fh:
            fh.write(json.dumps({
                "timestamp": "2026-09-02T10:00:00.000Z", "type": "session_meta",
                "payload": {"session_id": sid, "id": sid, "cwd": "/home/example/demo",
                            "originator": "Claude Code", "source": "exec",
                            "thread_source": "user"}}) + "\n")
            fh.write(json.dumps({
                "timestamp": "2026-09-02T10:00:01.000Z", "type": "response_item",
                "payload": {"type": "message", "role": "user",
                            "content": [{"type": "input_text",
                                         "text": "そうじゃなくて、先に射程を書いて"}]}}) + "\n")
        files = {f.session_id: f
                 for f in log_sources.CodexSessionsSource([tmp]).iter_files()}
        self.assertIn(sid, files)
        self.assertEqual([r["originator"] for r in files[sid].records()][0],
                         "Claude Code")
        self.assertTrue(files[sid].is_sidechain,
                        "originator=Claude Code のセッションは自分の発話ではない")
        recs = list(files[sid].records())
        self.assertTrue(recs, "レコードが1件も出ていない（検査が空振りしている）")
        for rec in recs:
            self.assertTrue(rec["is_sidechain"])

    def test_prompt_source_is_the_session_origin(self):
        self.assertEqual([r["prompt_source"] for r in self.files[S1].records()][0],
                         "exec")
        self.assertEqual([r["prompt_source"] for r in self.files[S3].records()][0],
                         "cli")

    def test_every_turn_is_emitted_exactly_once(self):
        # The fixture repeats one assistant turn on THREE channels
        # (response_item, event_msg/agent_message, event_msg/item_completed).
        recs = list(self.files[S1].records())
        self.assertEqual([r["role"] for r in recs],
                         ["user", "assistant", "user", "assistant"])
        self.assertEqual(sum(1 for r in recs
                             if r["text"] == "Three bullets, coming up."), 1)

    def test_injected_parts_are_dropped_per_part(self):
        recs = list(self.files[S1].records())
        first = recs[0]
        self.assertEqual(first["text"],
                         "Summarise the release notes in three bullets.")
        # the harness's context rode in the SAME message and is gone
        self.assertNotIn("environment_context", first["text"])
        # a message that is nothing but harness noise produces no record at all
        self.assertFalse(any("recommended_plugins" in r["text"] for r in recs))

    def test_developer_turns_are_not_conversation(self):
        for rec in self.files[S1].records():
            self.assertIn(rec["role"], ("user", "assistant"))
            self.assertNotIn("skills_instructions", rec["text"])

    def test_content_is_normalised_to_claude_blocks(self):
        # so a caller with its own stricter text_of reads both CLIs the same way
        rec = list(self.files[S1].records())[0]
        self.assertEqual(rec["raw_content"],
                         [{"type": "text",
                           "text": "Summarise the release notes in three bullets."}])

    def test_broken_lines_do_not_stop_the_file(self):
        recs = list(self.files[S3].records())
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["text"], "やめて、その方針は違う。")

    def test_line_numbers_are_physical(self):
        # fixture 3: header, blank, garbage, payload-less record, THE TURN.
        # Counting only parseable lines would call it line 2.
        self.assertEqual(list(self.files[S3].records())[0]["line"], 5)

    def test_every_field_is_present_on_every_record(self):
        want = {"source", "kind", "role", "msg_role", "ts", "text",
                "raw_content", "session_id", "parent_id", "path", "line",
                "cwd", "is_sidechain", "is_meta", "is_tool_result",
                "prompt_source", "originator"}
        for rec in self.src.iter_records():
            self.assertEqual(set(rec), want)
            self.assertEqual(rec["source"], CODEX)


class ClaudeUnchanged(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dir = os.path.join(self.tmp, "-home-example-demo")
        self.path = write_claude_log(self.dir)
        self.recs = list(log_sources.ClaudeProjectsSource([self.dir]).iter_records())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_only_user_and_assistant_records(self):
        self.assertEqual([r["kind"] for r in self.recs],
                         ["user", "assistant", "user", "user", "user", "user"])

    def test_bare_string_content_survives(self):
        # the bug that once dropped EVERY human turn
        self.assertEqual(self.recs[0]["text"], "やめて")

    def test_typed_blocks_are_joined_and_non_text_ignored(self):
        self.assertEqual(self.recs[1]["text"], "Understood.")

    def test_the_flags_the_scanners_filter_on(self):
        self.assertTrue(self.recs[2]["is_tool_result"])
        self.assertTrue(self.recs[3]["is_sidechain"])
        self.assertTrue(self.recs[4]["is_meta"])
        self.assertEqual(self.recs[5]["prompt_source"], "tool_injected")
        self.assertEqual(self.recs[0]["prompt_source"], "typed")

    def test_session_id_is_the_filename_stem(self):
        # correction_scan persists this as half of an event's identity, and
        # mine_conversations displays its first 8 characters.
        stem = os.path.basename(self.path)[:-len(".jsonl")]
        self.assertEqual(self.recs[0]["session_id"], stem)

    def test_line_numbers_are_physical(self):
        self.assertEqual([r["line"] for r in self.recs], [1, 2, 3, 4, 5, 6])


class ClaudeAbsorbedInput(unittest.TestCase):
    """Synthetic queue evidence only; never open the operator's real logs."""

    TEXT = "no, use the other file instead"
    TS = "2026-11-01T10:15:30.123Z"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.path = os.path.join(self.tmp, "synthetic-session.jsonl")

    def queue(self, operation="enqueue", text=None, **kw):
        return dict({"type": "queue-operation", "operation": operation,
                     "timestamp": self.TS, "content": self.TEXT if text is None else text}, **kw)

    def remove(self, text=None, **kw):
        return self.queue("remove", text, **dict({"reason": "absorbed_mid_turn"}, **kw))

    def user(self, text=None, **kw):
        return dict({"type": "user", "timestamp": self.TS,
                     "message": {"role": "user", "content": self.TEXT if text is None else text}}, **kw)

    def assistant(self, text="Earlier assistant context"):
        return {"type": "assistant", "timestamp": self.TS,
                "message": {"role": "assistant", "content": text}}

    def attachment(self, delivery="d1", origin="human", text=None, **kw):
        return {"type": "attachment", "attachment": dict({
            "type": "queued_command", "commandMode": "prompt", "origin": {"kind": origin},
            "humanTurn": False, "prompt": self.TEXT if text is None else text,
            "delivery_id": delivery, "source_uuid": "synthetic-source", "timestamp": self.TS}, **kw)}

    def read(self, *rows):
        with open(self.path, "w", encoding="utf-8") as fh:
            for row in rows:
                fh.write((row if isinstance(row, str) else json.dumps(row, ensure_ascii=False)) + "\n")
        return list(log_sources.ClaudeProjectsSource([self.tmp]).iter_records())

    def harvest(self):
        cands, files = correction_scan.harvest(
            [log_sources.ClaudeProjectsSource([self.tmp])], [("no,", re.compile("no,"))],
            datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc), 300, 160)
        self.assertEqual(files, 1)
        return cands

    def test_absorbed_enqueue_is_a_user_at_its_physical_line(self):
        recs = self.read(self.assistant(), "", "not JSON", self.queue(), self.remove())
        self.assertEqual([(r["kind"], r["line"]) for r in recs],
                         [("assistant", 1), ("user", 4)])
        rec = recs[1]
        self.assertEqual((rec["role"], rec["msg_role"], rec["raw_content"], rec["ts"]),
                         ("user", "user", self.TEXT, self.TS))
        self.assertEqual(rec["prompt_source"], "queued")
        cands = self.harvest()
        self.assertEqual([(c["line"], c["prior"]) for c in cands],
                         [(4, "Earlier assistant context")])

    def test_input_sent_with_an_image_is_kept(self):
        # With an image the attachment prompt is a list of parts; the queue
        # line carries only the typed text. Seen once in ~420 real inputs.
        parts = [{"type": "text", "text": self.TEXT},
                 {"type": "image", "source": {"type": "base64", "data": ""}}]
        recs = self.read(self.queue(), self.remove(deliveryId="d1"),
                         self.attachment(text=parts))
        self.assertEqual([(r["kind"], r["line"]) for r in recs], [("user", 1)])
        other = [{"type": "text", "text": "something else"}]
        self.assertEqual(self.read(self.queue(), self.remove(deliveryId="d1"),
                                   self.attachment(text=other)), [])
        self.assertEqual(self.read(self.queue(), self.remove(deliveryId="d1"),
                                   self.attachment(text=[{"type": "image"}])), [])

    def test_following_user_wins_and_is_harvested_once(self):
        recs = self.read(self.queue(), self.remove(), self.user())
        self.assertEqual([r["line"] for r in recs], [3])
        self.assertEqual([c["line"] for c in self.harvest()], [3])

    def test_queue_without_absorbed_remove_is_not_a_turn(self):
        for rows in ((self.queue(),), (self.remove(),),
                     (self.queue(), self.queue("dequeue")),
                     (self.queue(), self.remove(reason="delivered_to_agent")),
                     (self.remove(), self.queue())):
            with self.subTest(rows=rows):
                self.assertEqual(self.read(*rows), [])
                self.assertEqual(self.harvest(), [])

    def test_terminal_operation_cannot_later_be_absorbed_again(self):
        for terminal in (self.queue("dequeue"), self.remove(reason="delivered_to_agent")):
            with self.subTest(terminal=terminal):
                self.assertEqual(self.read(self.queue(), terminal, self.remove()), [])

    def test_pairing_is_by_exact_content(self):
        self.assertEqual(self.read(self.queue(), self.remove(text=self.TEXT + "!")), [])

    def test_pairs_never_cross_files(self):
        self.read(self.queue())
        other = os.path.join(self.tmp, "other-session.jsonl")
        with open(other, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(self.remove()) + "\n")
        self.assertEqual(list(log_sources.ClaudeProjectsSource([self.tmp]).iter_records()), [])

    def test_two_identical_inputs_are_two_turns(self):
        recs = self.read(self.queue(), self.remove(), self.queue(), self.remove())
        self.assertEqual([r["line"] for r in recs], [1, 3])
        cands = self.harvest()
        self.assertEqual(len(cands), 2)
        self.assertNotEqual(cands[0]["key"], cands[1]["key"])

    def test_one_remove_can_only_confirm_one_enqueue(self):
        self.assertEqual([r["line"] for r in self.read(
            self.queue(), self.queue(), self.remove())], [1])

    def test_one_enqueue_cannot_be_confirmed_twice(self):
        self.assertEqual([r["line"] for r in self.read(
            self.queue(), self.remove(), self.remove())], [1])

    def test_earlier_user_does_not_cancel_later_absorbed_input(self):
        recs = self.read(self.user(), self.queue(), self.remove())
        self.assertEqual([r["line"] for r in recs], [1, 2])
        self.assertEqual(len(self.harvest()), 2)

    def test_assistant_is_a_hard_duplicate_boundary_even_without_text(self):
        for text in ("continued", ""):
            with self.subTest(text=text):
                recs = self.read(self.queue(), self.remove(), self.assistant(text), self.user())
                self.assertEqual([r["line"] for r in recs if r["kind"] == "user"], [1, 4])

    def test_matching_users_are_consumed_once_in_order(self):
        recs = self.read(self.queue(), self.queue(), self.remove(), self.remove(), self.user())
        self.assertEqual([r["line"] for r in recs], [2, 5])
        recs = self.read(self.queue(), self.queue(), self.remove(), self.remove(), self.user(), self.user())
        self.assertEqual([r["line"] for r in recs], [5, 6])

    def test_nearest_following_user_cannot_cancel_a_later_enqueue(self):
        recs = self.read(self.queue(), self.remove(), self.user(), self.queue(), self.remove())
        self.assertEqual([r["line"] for r in recs], [3, 4])

    def test_nonhuman_user_cannot_hide_a_queued_human_input(self):
        for flags in ({"isSidechain": True}, {"isMeta": True}, {"isCompactSummary": True},
                      {"toolUseResult": {}}, {"promptSource": "tool_injected"}):
            with self.subTest(flags=flags):
                # Ordinary records retain their old behavior; they cannot own
                # the human queue record for purposes of duplicate removal.
                recs = self.read(self.queue(), self.remove(), self.user(**flags))
                self.assertEqual([r["line"] for r in recs], [1, 3])

    def test_attachment_origin_human_counts_even_when_human_turn_is_false(self):
        recs = self.read(self.queue(), self.remove(deliveryId="d1"), self.attachment())
        self.assertEqual([r["line"] for r in recs], [1])
        self.assertEqual(len(self.harvest()), 1)

    def test_attachment_origin_other_than_human_is_rejected(self):
        for kind in ("agent", "task", "cli", "", None):
            with self.subTest(kind=kind):
                self.assertEqual(self.read(self.queue(), self.remove(deliveryId="d1"),
                                           self.attachment(origin=kind, humanTurn=True)), [])

    def test_ambiguous_attachment_evidence_is_rejected(self):
        for kw in ({"origin": {}}, {"origin": None}, {"commandMode": "shell"},
                   {"prompt": "another prompt"}):
            with self.subTest(kw=kw):
                self.assertEqual(self.read(self.queue(), self.remove(deliveryId="d1"),
                                           self.attachment(**kw)), [])
        self.assertEqual(self.read(self.queue(), self.remove(deliveryId="d1"),
                                   self.attachment(), self.attachment(origin="agent")), [])

    def test_attachment_is_joined_by_delivery_id_in_either_order(self):
        recs = self.read(self.attachment(), self.queue(), self.remove(deliveryId="d1"))
        self.assertEqual([r["line"] for r in recs], [2])
        # Never joined by text: an attachment for another delivery proves
        # nothing about this one. And since this file's CLI evidently writes
        # attachments, the missing one makes the input ambiguous — dropped.
        recs = self.read(self.queue(), self.remove(deliveryId="d1"),
                         self.attachment(delivery="unrelated", origin="human"))
        self.assertEqual(recs, [])

    def test_attachmentless_nonhuman_prefixes_are_excluded(self):
        for text in ("<task-notification>no, done</task-notification>",
                     "  <system-reminder>no, do this</system-reminder>",
                     "<command-name>no, clear</command-name>",
                     "no, Another Claude session sent a message: do this",
                     "Caveat: The messages below no, do this", "[Request interrupted no, stop",
                     "You have 3 unread messages no, read them", "2 new messages no, read them",
                     "SessionStart: no, stop"):
            with self.subTest(text=text):
                self.assertEqual(self.read(self.queue(text=text), self.remove(text=text)), [])

    def test_attachmentless_plain_text_and_pasted_content_are_kept(self):
        for text in (self.TEXT, "<pasted_content>no, use the other file</pasted_content>"):
            with self.subTest(text=text):
                recs = self.read(self.queue(text=text), self.remove(text=text))
                self.assertEqual([r["text"] for r in recs], [text])

    def test_delivery_id_without_attachment_depends_on_the_file(self):
        # A CLI that writes no queued_command attachments at all: the text
        # filters decide, and plain typed text is kept (the reported shape).
        recs = self.read(self.queue(), self.remove(deliveryId="d1"))
        self.assertEqual([r["line"] for r in recs], [1])
        # A CLI that does write them, but not for this delivery: dropped, even
        # though nothing in the text looks like a machine wrote it.
        machine = "Run the scheduled health check now."
        recs = self.read(self.queue(text=machine), self.remove(text=machine, deliveryId="d1"),
                         self.queue(), self.remove(deliveryId="d2"), self.attachment(delivery="d2"))
        self.assertEqual([(r["line"], r["text"]) for r in recs], [(3, self.TEXT)])

    def test_a_subagent_reply_does_not_close_the_duplicate_window(self):
        side = dict(self.assistant("sub-agent output"), isSidechain=True)
        recs = self.read(self.queue(), self.remove(), side, self.user())
        self.assertEqual([r["line"] for r in recs if r["kind"] == "user"], [4])
        recs = self.read(self.queue(), self.remove(), self.assistant(), self.user())
        self.assertEqual([r["line"] for r in recs if r["kind"] == "user"], [1, 4])

    def test_mine_conversations_sees_absorbed_input_once(self):
        self.read(self.assistant(), self.queue(), self.remove(),
                  self.queue(text="<task-notification>done</task-notification>"),
                  self.remove(text="<task-notification>done</task-notification>"))
        out = os.path.join(self.tmp, "out")
        env = {k: v for k, v in os.environ.items()
               if k not in ("LOG_SOURCE", "CODEX_SESSIONS_DIR", "CODEX_CWD_FILTER",
                            "DISTILL_LOG_DIRS", "CONV_DIRS")}
        p = subprocess.run([sys.executable, os.path.join(REPO, "scripts", "mine_conversations.py"),
                            "--source", "claude", "--dirs", self.tmp, "--out", out],
                           capture_output=True, text=True, env=env)
        self.assertEqual(p.returncode, 0, p.stderr)
        with open(os.path.join(out, "corpus.jsonl"), encoding="utf-8") as fh:
            corpus = [json.loads(x) for x in fh]
        self.assertEqual([r["text"] for r in corpus], [self.TEXT])

    def test_queued_sidechain_meta_and_nonhuman_source_are_excluded(self):
        for flags in ({"isSidechain": True}, {"isMeta": True}, {"isCompactSummary": True},
                      {"toolUseResult": {}}, {"promptSource": "tool_injected"}):
            with self.subTest(flags=flags):
                self.assertEqual(self.read(self.queue(**flags), self.remove()), [])
        for flags in ({"isSidechain": True}, {"isMeta": True}):
            with self.subTest(removal_flags=flags):
                self.assertEqual(self.read(self.queue(), self.remove(**flags)), [])

    def test_normal_user_origin_behavior_is_unchanged(self):
        recs = self.read(self.user(origin={"kind": "agent"}))
        self.assertEqual([r["line"] for r in recs], [1])

    def test_enqueue_can_be_reopened_but_unconfirmed_queue_cannot(self):
        recs = self.read(self.queue(), self.remove())
        line = json.dumps(self.queue())
        for header in (None, log_sources.header_for(self.path, CLAUDE)):
            self.assertEqual(log_sources.record_from_line(line, self.path, 1, CLAUDE, header), recs[0])
        self.read(self.queue())
        self.assertIsNone(log_sources.record_from_line(line, self.path, 1, CLAUDE))

    def test_show_event_reopens_the_enqueue_and_detects_text_changes(self):
        self.read(self.assistant(), "not JSON", self.queue(), self.remove(), self.assistant("after"))
        patterns = os.path.join(self.tmp, "patterns.txt")
        material = os.path.join(self.tmp, "material.md")
        with open(patterns, "w", encoding="utf-8") as fh:
            fh.write("no,\n")
        command = [sys.executable, os.path.join(REPO, "scripts", "correction_scan.py")]
        env = dict(os.environ, LOG_SOURCE="claude")
        scan = subprocess.run(command + ["--patterns", patterns, "--material", material,
                              "--state", os.path.join(self.tmp, "state.json"), "--since", "36500",
                              "--dir", self.tmp], capture_output=True, text=True, env=env)
        self.assertEqual(scan.returncode, 0, scan.stderr)
        with open(material + ".index.jsonl", encoding="utf-8") as fh:
            index = [json.loads(row) for row in fh]
        self.assertEqual(len(index), 1)
        self.assertEqual(index[0]["line"], 3)
        def show():
            return subprocess.run(command + ["--material", material, "--show-event", index[0]["event"],
                                             "--context", "1"], capture_output=True, text=True, env=env)
        shown = show()
        self.assertEqual(shown.returncode, 0, shown.stderr)
        self.assertIn(self.path + ":3", shown.stdout)
        self.assertIn(self.TEXT, shown.stdout)
        self.assertIn("Earlier assistant context", shown.stdout)
        self.assertIn("after", shown.stdout)
        self.assertNotIn("no longer", shown.stdout)
        self.assertNotIn("CONTENT CHANGED", shown.stdout)
        changed = self.TEXT + " (changed)"
        self.read(self.assistant(), "not JSON", self.queue(text=changed), self.remove(text=changed))
        shown = show()
        self.assertEqual(shown.returncode, 0, shown.stderr)
        self.assertIn("CONTENT CHANGED", shown.stdout)
        self.assertIn(changed, shown.stdout)

    def test_show_event_keeps_old_enqueue_provenance_after_user_is_appended(self):
        self.read(self.queue(), self.remove())
        patterns = os.path.join(self.tmp, "patterns.txt")
        material = os.path.join(self.tmp, "material.md")
        with open(patterns, "w", encoding="utf-8") as fh:
            fh.write("no,\n")
        command = [sys.executable, os.path.join(REPO, "scripts", "correction_scan.py")]
        env = dict(os.environ, LOG_SOURCE="claude")
        scan = subprocess.run(command + ["--patterns", patterns, "--material", material,
                              "--state", os.path.join(self.tmp, "state.json"), "--since", "36500",
                              "--dir", self.tmp], capture_output=True, text=True, env=env)
        self.assertEqual(scan.returncode, 0, scan.stderr)
        with open(material + ".index.jsonl", encoding="utf-8") as fh:
            index = [json.loads(row) for row in fh]
        self.assertEqual(len(index), 1)
        self.assertEqual(index[0]["line"], 1)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(self.user()) + "\n")
        # New harvests prefer user at line 3; the old indexed source remains
        # a readable enqueue at line 1, with unchanged content and checksum.
        self.assertEqual([r["line"] for r in
                          log_sources.ClaudeProjectsSource([self.tmp]).iter_records()], [3])
        shown = subprocess.run(command + ["--material", material, "--show-event", index[0]["event"],
                                          "--context", "0"], capture_output=True, text=True, env=env)
        self.assertEqual(shown.returncode, 0, shown.stderr)
        self.assertIn(self.path + ":1", shown.stdout)
        self.assertIn(">>> the correction, in full:", shown.stdout)
        self.assertIn(self.TEXT, shown.stdout)
        self.assertNotIn("no longer", shown.stdout)
        self.assertNotIn("CONTENT CHANGED", shown.stdout)


class SourceSelection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.claude_dir = os.path.join(self.tmp, "claude", "-home-example-demo")
        write_claude_log(self.claude_dir)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        os.environ.pop("LOG_SOURCE", None)
        os.environ.pop("CODEX_CWD_FILTER", None)

    def test_auto_joins_both_in_reading_order(self):
        srcs = log_sources.build_sources(
            "auto", claude_dirs=[self.claude_dir], codex_dirs=[FIXTURES])
        self.assertEqual([s.name for s in srcs], [CLAUDE, CODEX])
        seen = {r["source"] for s in srcs for r in s.iter_records()}
        self.assertEqual(seen, {CLAUDE, CODEX})

    def test_auto_skips_a_cli_with_no_logs(self):
        srcs = log_sources.build_sources(
            "auto", claude_dirs=[os.path.join(self.tmp, "nope")],
            codex_dirs=[FIXTURES])
        self.assertEqual([s.name for s in srcs], [CODEX])

    def test_naming_a_cli_returns_it_even_when_empty(self):
        # "you asked for Codex and there are none" is the caller's error to
        # report; a silent empty scan looks exactly like a quiet week.
        srcs = log_sources.build_sources(CODEX,
                                         codex_dirs=[os.path.join(self.tmp, "nope")])
        self.assertEqual([s.name for s in srcs], [CODEX])
        self.assertEqual(srcs[0].existing_dirs(), [])

    def test_naming_a_directory_scopes_the_run_to_that_cli(self):
        self.assertEqual(log_sources.resolve_source_name(claude_named=True), CLAUDE)
        self.assertEqual(log_sources.resolve_source_name(codex_named=True), CODEX)
        self.assertEqual(log_sources.resolve_source_name(), "auto")
        self.assertEqual(
            log_sources.resolve_source_name(claude_named=True, codex_named=True),
            "auto")

    def test_an_explicit_source_beats_the_environment(self):
        os.environ["LOG_SOURCE"] = CLAUDE
        self.assertEqual(log_sources.resolve_source_name(CODEX), CODEX)
        self.assertEqual(log_sources.resolve_source_name(claude_named=False), CLAUDE)

    def test_unknown_source_is_an_error(self):
        self.assertRaises(ValueError, log_sources.build_sources, "gemini")

    def test_cwd_filter_can_come_from_the_environment(self):
        # a scheduled job says it once in config.env, not on every line
        os.environ["CODEX_CWD_FILTER"] = "/home/example/other"
        try:
            srcs = log_sources.build_sources(CODEX, codex_dirs=[FIXTURES])
            self.assertEqual(list(srcs[0].iter_files()), [])
        finally:
            os.environ.pop("CODEX_CWD_FILTER", None)

    def test_cwd_filter_scopes_codex_to_one_project(self):
        # Codex files every project into one tree, so this is the only scope
        # there is; without it a scan run in one repo reports on all of them.
        keep = log_sources.CodexSessionsSource([FIXTURES],
                                               cwd_filter=["/home/example/demo"])
        drop = log_sources.CodexSessionsSource([FIXTURES],
                                               cwd_filter=["/home/example/other"])
        self.assertEqual(sorted(sf.session_id for sf in keep.iter_files()),
                         [S1, S2, S3])
        self.assertEqual([sf.session_id for sf in drop.iter_files()], [])


class SinceWindow(unittest.TestCase):
    """The window is read off the FILES' mtimes, so every age these tests
    depend on has to be set here — none of it may be inherited from the
    checkout.

    shutil.copytree copies with copy2, which carries mtime across. A plain
    copy therefore handed these tests whatever date the working tree happened
    to be written, and once that date fell outside the cutoff the two files
    that are supposed to be INSIDE the window dropped out of it: red with no
    code change, on nothing but the calendar. CI never saw it because
    actions/checkout rewrites the tree on every run. _stage() closes that by
    pinning every copied file to "now" and ageing by hand only the one file
    the assertions want stale.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.tree, self.paths = self._stage()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _stage(self, source=FIXTURES, name="sessions"):
        """Copy the fixtures and OWN their mtimes: all fresh, then one stale."""
        tree = os.path.join(self.tmp, name)
        shutil.copytree(source, tree)
        paths = sorted(
            os.path.join(dp, fn)
            for dp, _, fns in os.walk(tree) for fn in fns)
        now = datetime.datetime.now().timestamp()
        for path in paths:              # discard whatever age came along
            os.utime(path, (now, now))
        old = now - 40 * 86400          # exactly one file, deliberately stale
        os.utime(paths[0], (old, old))
        return tree, paths

    @staticmethod
    def _cutoff(days):
        return datetime.datetime.now(datetime.timezone.utc) - \
            datetime.timedelta(days=days)

    def test_mtime_cutoff_drops_the_stale_file(self):
        src = log_sources.CodexSessionsSource([self.tree])
        self.assertEqual(len(list(src.iter_files())), 3)
        self.assertEqual(len(list(src.iter_files(self._cutoff(7)))), 2)

    def test_no_cutoff_reads_everything(self):
        src = log_sources.CodexSessionsSource([self.tree])
        self.assertEqual(len(list(src.iter_files(None))), 3)

    def test_the_window_does_not_depend_on_the_checkouts_age(self):
        # the regression itself: stage from a source tree that was written a
        # month ago. Without the pinning loop the copy inherits those mtimes
        # and a 7-day cutoff keeps 0 files instead of 2.
        stale = os.path.join(self.tmp, "stale_checkout")
        shutil.copytree(FIXTURES, stale)
        month_ago = datetime.datetime.now().timestamp() - 30 * 86400
        for dirpath, _, names in os.walk(stale):
            for name in names:
                os.utime(os.path.join(dirpath, name), (month_ago, month_ago))
        tree, _ = self._stage(source=stale, name="from_a_stale_checkout")
        src = log_sources.CodexSessionsSource([tree])
        self.assertEqual(len(list(src.iter_files())), 3)
        self.assertEqual(len(list(src.iter_files(self._cutoff(7)))), 2)


class SinceParsing(unittest.TestCase):
    def test_day_counts(self):
        self.assertEqual(log_sources.parse_since("7d"), 7)
        self.assertEqual(log_sources.parse_since("7"), 7)
        self.assertIsNone(log_sources.parse_since(None))
        self.assertEqual(log_sources.parse_since("", default=1), 1)

    def test_an_absolute_date_becomes_a_day_count(self):
        today = datetime.datetime.now(datetime.timezone.utc)
        two_ago = (today - datetime.timedelta(days=2)).strftime("%Y-%m-%d")
        self.assertEqual(log_sources.parse_since(two_ago), 3)
        self.assertEqual(log_sources.parse_since(today.strftime("%Y-%m-%d")), 1)

    def test_nonsense_is_the_callers_to_report(self):
        self.assertRaises(ValueError, log_sources.parse_since, "last tuesday")


class ReopenOneLine(unittest.TestCase):
    """correction_scan --show-event reopens a line months later, with nothing
    but the path to say which CLI wrote it."""

    def test_source_is_recoverable_from_the_filename(self):
        codex = os.path.join(FIXTURES, "2026", "09", "01",
                             "rollout-2026-09-01T10-00-00-%s.jsonl" % S1)
        self.assertEqual(log_sources.source_of_path(codex), CODEX)
        self.assertEqual(log_sources.source_of_path("/x/%s.jsonl" % S1), CLAUDE)

    def test_one_line_reparses_to_the_same_record(self):
        codex = os.path.join(FIXTURES, "2026", "09", "01",
                             "rollout-2026-09-01T10-00-00-%s.jsonl" % S1)
        header = log_sources.header_for(codex)
        with open(codex, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        want = list(log_sources.CodexSessionsSource([FIXTURES]).iter_records())
        want = [r for r in want if r["path"] == codex][0]
        got = log_sources.record_from_line(lines[want["line"] - 1], codex,
                                           want["line"], CODEX, header)
        self.assertEqual(got["text"], want["text"])
        self.assertEqual(got["session_id"], want["session_id"])


class ScriptsEndToEnd(unittest.TestCase):
    """The three consumers, run as the docs tell you to run them."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_script(self, name, *args):
        env = dict(os.environ)
        env.pop("LOG_SOURCE", None)
        env.pop("CODEX_SESSIONS_DIR", None)
        env.pop("CODEX_CWD_FILTER", None)
        env.pop("DISTILL_LOG_DIRS", None)
        env.pop("CONV_DIRS", None)
        return subprocess.run(
            [sys.executable, os.path.join(REPO, "scripts", name)] + list(args),
            capture_output=True, text=True, env=env)

    def test_mine_conversations_reads_codex(self):
        p = self.run_script("mine_conversations.py", "--source", "codex",
                            "--codex-dir", FIXTURES, "--out", self.tmp)
        self.assertEqual(p.returncode, 0, p.stderr)
        with open(os.path.join(self.tmp, "corpus.jsonl"), encoding="utf-8") as fh:
            corpus = [json.loads(x) for x in fh]
        # two human turns in the user session, one in the half-written file.
        # The sub-agent's turn is not the human's and must not be here.
        self.assertEqual(len(corpus), 3)
        self.assertEqual({r["cli"] for r in corpus}, {CODEX})
        self.assertEqual({r["session"] for r in corpus}, {S1[:8], S3[:8]})
        self.assertNotIn("environment_context", corpus[0]["text"])
        self.assertNotIn("recommended_plugins", corpus[0]["text"])

    def test_correction_scan_harvests_codex(self):
        pat = os.path.join(self.tmp, "patterns.txt")
        with open(pat, "w", encoding="utf-8") as fh:
            fh.write("そうじゃなく\nやめて\n")
        mat = os.path.join(self.tmp, "material.md")
        p = self.run_script("correction_scan.py", "--patterns", pat,
                            "--material", mat,
                            "--state", os.path.join(self.tmp, "state.json"),
                            "--since", "36500", "--source", "codex",
                            "--codex-dir", FIXTURES)
        self.assertEqual(p.returncode, 0, p.stderr)
        with open(mat + ".index.jsonl", encoding="utf-8") as fh:
            index = [json.loads(x) for x in fh]
        # the sub-agent said "そうじゃなく" too, and must not be harvested
        self.assertEqual({r["session"] for r in index}, {S1, S3})
        self.assertEqual({r["log_source"] for r in index}, {CODEX})

    def test_discipline_scan_reads_codex(self):
        cat = os.path.join(self.tmp, "catalog.yaml")
        with open(cat, "w", encoding="utf-8") as fh:
            fh.write("disciplines:\n"
                     "  - id: X1\n"
                     "    type: trace\n"
                     "    name: a synthetic discipline\n"
                     "    origin: unit-test\n"
                     "    role: user\n"
                     "    fire: 'そうじゃなく'\n")
        out = os.path.join(self.tmp, "report.md")
        p = self.run_script("discipline_scan.py", "--catalog", cat,
                            "--since", "36500", "--source", "codex",
                            "--codex-dir", FIXTURES, "--out", out)
        self.assertEqual(p.returncode, 0, p.stderr)
        with open(out, encoding="utf-8") as fh:
            body = fh.read()
        self.assertIn("X1", body)
        # sub=1 marks the sub-agent turn; discipline_scan reports rather than
        # drops it, so the flag has to survive the adapter
        self.assertIn("sub=1", body)

    def test_a_named_directory_that_is_missing_is_fatal(self):
        p = self.run_script("discipline_scan.py", "--catalog",
                            os.path.join(REPO, "tests", "fixtures",
                                         "discipline_catalog.yaml"),
                            "--codex-dir", os.path.join(self.tmp, "nope"))
        self.assertEqual(p.returncode, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
