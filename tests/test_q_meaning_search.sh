#!/usr/bin/env bash
# shellcheck shell=bash
# shellcheck disable=SC2154  # globals come from scripts/test.sh

group "Q. meaning search (fictional inputs, real adapter, stub models)"

Q_ROOT="$TEST_TMP/q_meaning_search"
Q_KIT="$Q_ROOT/kit"
Q_BIN="$Q_ROOT/bin"
Q_INPUT="$Q_ROOT/input"
Q_TMP="$Q_ROOT/tmp"
Q_TRACE="$Q_ROOT/trace"
Q_HOST_PATH="$PATH"
mkdir -p "$Q_KIT/templates/skills" "$Q_KIT/scripts" "$Q_BIN" "$Q_INPUT/transcripts" "$Q_TMP" "$Q_TRACE"
cp -R "$REPO_ROOT/scripts/lib" "$Q_KIT/scripts/"
cp -R "$REPO_ROOT/templates/skills/meaning-search" "$Q_KIT/templates/skills/"
Q_SKILL="$Q_KIT/templates/skills/meaning-search"
Q_SEARCH="$Q_SKILL/scripts/meaning_search.py"
Q_AGENT="$Q_SKILL/scripts/ms_agent.sh"
Q_SCORE="$Q_SKILL/scripts/score.py"
Q_SAMPLE="$Q_SKILL/sample"
Q_TRAP_LOG="$Q_ROOT/unexpected-cli"

for Q_FILE in scripts/meaning_search.py scripts/ms_agent.sh scripts/score.py scripts/try_sample.sh \
    prompts/common.md prompts/scan.md prompts/terms.md prompts/verbatim.md mishearings.md.example \
    sample/ledger.yaml sample/decisions_journal.md sample/glossary.md sample/mishearings.md sample/answer_key.json; do
  assert_file "Q1: ships $Q_FILE" "$Q_SKILL/$Q_FILE"
done
assert_eq "Q1: the fictional sample has two transcripts" 2 "$(find "$Q_SAMPLE/transcripts" -type f | wc -l)"

cat > "$Q_BIN/claude" <<'SHIM'
#!/usr/bin/env bash
printf '%s\n' "$0" >> "$Q_TRAP_LOG"
exit 96
SHIM
cp "$Q_BIN/claude" "$Q_BIN/codex"

# One trace file per call keeps concurrent writes separate. The rule file
# controls the selected IDs, the injected answers, and the failing calls.
cat > "$Q_BIN/meaning-stub" <<'STUB'
#!/usr/bin/env python3
import json
import os
from pathlib import Path
import re
import sys
import tempfile

argv = sys.argv[1:]
stdin = sys.stdin.read()
prompt = stdin or (argv[1] if argv[0] == "-p" else argv[-1])
trace = Path(os.environ["Q_TRACE"])
rules = json.loads(Path(os.environ["Q_RULES"]).read_text(encoding="utf-8"))
with tempfile.NamedTemporaryFile(dir=trace, suffix=".json", mode="w", encoding="utf-8", delete=False) as log:
    json.dump({"argv": argv, "stdin": stdin, "prompt": prompt,
               "cwd": os.getcwd(), "cwd_entries": sorted(os.listdir())}, log, ensure_ascii=False)

if "<records>\n" in prompt:
    body = prompt.split("<records>\n", 1)[1].split("\n</records>", 1)[0]
    ids = set(re.findall(r"(?m)^(?:\s*- id: |### )(\S+)", body))
    if rules.get("fail_first") in ids:
        try:
            (trace / "failed-once").touch(exist_ok=False)
        except FileExistsError:
            pass
        else:
            sys.exit(8)
    if rules.get("invalid_json") in ids:
        print("{broken JSON")
        sys.exit(0)
    hits = rules.get("chunk_hits", {}).get(" ".join(sorted(ids)))
    if hits is None:
        hits = dict.fromkeys(sorted(ids.intersection(rules.get("hits", []))), "直接")
    for target, fake_ids in rules.get("extra_ids", {}).items():
        if target in ids:
            hits.update(dict.fromkeys(fake_ids, "直接"))
    result = {"hits": [
        {"id": hit, "section": "facts", "what": "fixture hit", "why": f"fixture reason {strength}",
         "strength": strength, "mishearing": ""} for hit, strength in hits.items()
    ]}
elif "<snippets>\n" in prompt:
    result = {"snippets": []}
    for snippet, file, low, high in re.findall(r'<snippet id="([^"]+)" file="([^"]+)" lines="L(\d+)-L(\d+)"', prompt):
        low, high = int(low), int(high)
        quote_lines = rules.get("quote_lines", {})
        ranges = [[n, n] for n in quote_lines.get(file, []) if low <= n <= high] if quote_lines else [[low, high]]
        passages = [{"lines": span, "says": "fixture range", "mishearing": "",
                     "text": "model text should never be quoted"} for span in ranges]
        if rules.get("invalid_passage"):
            passages.append({"lines": [high, high + 1], "says": "outside the snippet", "mishearing": ""})
        result["snippets"].append({"snippet": snippet, "relevant": True, "summary": "", "passages": passages})
elif "論点の言い換え・関係語・聞き違いの語を出す" in prompt:
    result = {"terms": [{"term": term, "kind": "言い換え"} for term in rules.get("terms", [])]}
else:
    result = {"echo": prompt}

answer = json.dumps(result, ensure_ascii=False)
if "<records>\n" in prompt:
    answer = "fixture prefix\n```json\n" + answer + "\n```\nfixture suffix"
if "-o" in argv:
    Path(argv[argv.index("-o") + 1]).write_text(answer, encoding="utf-8")
else:
    print(answer)
STUB
chmod +x "$Q_BIN/claude" "$Q_BIN/codex" "$Q_BIN/meaning-stub"

Q_RULES="$Q_ROOT/baseline.json"
cat > "$Q_RULES" <<'EOF_BASELINE'
{
  "hits": ["F-001", "F-002", "F-003", "F-004", "F-005", "F-006", "F-007", "F-008", "F-011"],
  "chunk_hits": {
    "F-001 F-002 F-003": {"F-001": "直接", "F-002": "直接"},
    "F-001": {"F-001": "関連"},
    "F-004 F-005 F-006": {"F-004": "周辺", "F-005": "直接", "F-006": "直接"},
    "F-002 F-003 F-004": {"F-003": "直接", "F-004": "関連"},
    "F-009 F-010": {"F-009": "関連"}
  },
  "extra_ids": {"F-001": ["Z-INVENTED", "F-CROSS"]},
  "invalid_passage": true,
  "quote_lines": {"notes.txt": [3, 5], "meeting-2026-01-12.txt": [3], "meeting-2026-01-13-b.txt": [3], "unclocked.txt": [2]},
  "terms": ["青箱点検", "record boundary marker"]
}
EOF_BASELINE

q_env() {
  env -i PATH="$Q_BIN:$Q_HOST_PATH" HOME="$Q_ROOT/home" TMPDIR="$Q_TMP" \
    Q_TRACE="$Q_TRACE" Q_RULES="$Q_RULES" Q_TRAP_LOG="$Q_TRAP_LOG" \
    MSEARCH_KIT_ROOT="$Q_KIT" AGENT_CLI=claude AGENT_CMD="$Q_BIN/meaning-stub" \
    AGENT_MODEL_FAST=fast-fixture-model "$@"
}

q_new_trace() {
  Q_TRACE="$Q_ROOT/trace-$1"
  mkdir "$Q_TRACE"
}

q_search() {
  q_env python3 "$Q_SEARCH" --topic fixture --ledger "$Q_INPUT/ledger.yaml" \
    --journal "$Q_INPUT/journal.md" --transcripts "$Q_INPUT/transcripts" \
    --source-root "$Q_INPUT" --chunk-tokens 180 --whole-meetings 0 --pad 1 --parallel 3 --retries 0 "$@"
}

q_trace_count() {
  find "$Q_TRACE" -maxdepth 1 -name '*.json' -type f | wc -l
}

q_check_skill_frontmatter() {
  python3 - "$Q_SKILL/SKILL.md" <<'PY'
from pathlib import Path
import re
import sys

document = Path(sys.argv[1]).read_text(encoding="utf-8")
frontmatter = re.match(r"---\n(.*?)\n---(?:\n|$)", document, re.DOTALL)
assert frontmatter, "missing opening or closing frontmatter fence"
assert re.search(r"^name: meaning-search\s*$", frontmatter[1], re.MULTILINE), "wrong skill name"
assert re.search(r"^description:", frontmatter[1], re.MULTILINE), "missing description"
assert re.search(r"\bbeta\b", document, re.IGNORECASE), "missing beta label"
PY
}
assert_ok "Q11: SKILL.md has fenced frontmatter, a name, a description, and a beta label" q_check_skill_frontmatter

q_check_skill_options() {
  local help
  help="$(q_env python3 "$Q_SEARCH" --help)" || return
  python3 - "$Q_SKILL/SKILL.md" "$help" <<'PY'
from pathlib import Path
import re
import sys

option = r"(?<![\w-])--[a-z][a-z0-9-]*(?![\w-])"
document = Path(sys.argv[1]).read_text(encoding="utf-8")
documented = set()
for line in document.splitlines():
    options = set(re.findall(option, line))
    if "Claude Code" in line:
        options.difference_update({"--tools", "--strict-mcp-config", "--no-session-persistence"})
    documented.update(options)
implemented = set(re.findall(r"^  (?:-h, )?(" + option + r")", sys.argv[2], re.MULTILINE))
assert documented, "no command-line options found in SKILL.md"
assert not (documented - implemented), sorted(documented - implemented)
PY
}
q_new_trace help
assert_ok "Q11: all meaning search options in SKILL.md appear in --help" q_check_skill_options
assert_eq "Q11: --help makes zero CLI calls" 0 "$(q_trace_count)"

q_check_custom_agent_help() {
  q_env python3 - "$Q_SEARCH" "$Q_SKILL/SKILL.md" <<'PY'
from pathlib import Path
import re
import subprocess
import sys

script, skill = sys.argv[1:]
help_text = subprocess.check_output([sys.executable, script, "--help"], text=True)
help_entry = re.search(r"^  --agent\b[^\n]*(?:\n {4,}\S[^\n]*)*", help_text, re.MULTILINE)
assert help_entry, help_text
docs = Path(skill).read_text(encoding="utf-8")
doc_entries = [line for line in docs.splitlines() if "--agent" in line]
for entries in ([help_entry[0]], doc_entries):
    assert any(re.search(r"試験|テスト", entry) and re.search(r"道具|ツール", entry)
               and "モデル" in entry and re.search(r"掛から|かから|しない|なし|無い|ない", entry)
               for entry in entries), entries
PY
}
assert_ok "Y5: help and SKILL.md explain that custom test agents bypass tool restrictions and model checks" q_check_custom_agent_help

python3 - "$Q_INPUT" <<'PY'
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
ledger = [
    ("F-001", '  source: "transcripts/notes.txt:3（注記）"'),
    ("F-002", '  source: "talk:00:00:35"\n  fresh: 20260112'),
    ("F-003", '  source: "talk:00:00:35"\n  fresh: 2026-01-13'),
    ("F-004", '  source: "talk:meeting-2026-01-13-b@00:00:35"'),
    ("F-005", '  source: "mail:2026-01-12"'),
    ("F-006", '  source: "untagged pointer"'),
    ("F-007", ''),
    ("F-008", '  source: "talk:unclocked@00:00:35"'),
    ("F-009", '  note: 青箱点検'),
    ("F-010", '  note: 青箱点検'),
    ("F-011", '  source: "transcripts/notes.txt:5"'),
    ("F-BIG", '  note: ' + '長' * 250),
    ("F-CROSS", ''),
]
ledger_records = []
for record_id, fields in ledger:
    text = f"  - id: {record_id}\n    title: Fixture entry {record_id} contains a record boundary marker"
    if fields:
        text += "\n" + "\n".join("  " + line for line in fields.splitlines())
    text += f"\n    tail: END-{record_id}"
    ledger_records.append(text)
(root / "ledger.yaml").write_text(
    "meta:\n  project: META-SENTINEL\nfacts:\n" + "\n\n".join(ledger_records) + "\n", encoding="utf-8"
)
journal_records = []
for number in range(1, 4):
    record_id = f"D-2026-01-12-0{number}"
    journal_records.append(f"### {record_id} Journal entry with enough text for the chunk test\n\nEND-{record_id}")
(root / "journal.md").write_text("# Journal\n\n" + "\n\n".join(journal_records) + "\n", encoding="utf-8")
(root / "expected.json").write_text(json.dumps(ledger_records + journal_records, ensure_ascii=False), encoding="utf-8")
for name in ("meeting-2026-01-12", "meeting-2026-01-13-a", "meeting-2026-01-13-b"):
    (root / "transcripts" / f"{name}.txt").write_text(
        "00:00:00 start\n00:00:15 check\n00:00:30 floor\n00:00:45 later\n00:01:00 finish\n",
        encoding="utf-8",
    )
for name in ("notes", "unclocked"):
    (root / "transcripts" / f"{name}.txt").write_text(
        "beginning\nsecond\n  original  spacing\nfourth\nlast line\n", encoding="utf-8"
    )
PY

Q_BEFORE="$(tree_hashes "$Q_INPUT")"
Q_SAMPLE_BEFORE="$(tree_hashes "$Q_SAMPLE")"
q_new_trace dry
Q_DRY_STATUS=0
Q_DRY_TEXT="$(q_search --out "$Q_ROOT/dry" --dry-run 2>&1)" || Q_DRY_STATUS=$?
assert_eq "Q9: dry run exits successfully" 0 "$Q_DRY_STATUS"
assert_eq "Q9: dry run makes zero CLI calls" 0 "$(q_trace_count)"
q_check_plan() {
  PYTHONUTF8=1 python3 - "$Q_ROOT/dry/plan.json" "$Q_INPUT/expected.json" "$Q_DRY_TEXT" <<'PY'
import json
from pathlib import Path
import re
import sys

plan, expected = [json.loads(Path(path).read_text(encoding="utf-8")) for path in sys.argv[1:3]]
chunks = plan["chunks"]
ids = [re.search(r"^(?:\s*- id: |### )(\S+)", record)[1] for record in expected]
per_pass = [[chunk["ids"] for chunk in chunks if chunk["pass"] == p] for p in (1, 2)]
for pass_chunks in per_pass:
    assert [record_id for chunk in pass_chunks for record_id in chunk] == ids, pass_chunks
assert per_pass[0] != per_pass[1], per_pass
oversize = [chunk for chunk in chunks if "F-BIG" in chunk["ids"]]
assert len(oversize) == 2 and all(c["ids"] == ["F-BIG"] and c["oversize"] for c in oversize), oversize
assert plan["planned_calls"] == len(chunks), plan
assert f"区切り {len(chunks)} 件・予定呼び出し {plan['planned_calls']} 回" in sys.argv[3], sys.argv[3]
PY
}
assert_ok "Q2/Q9: plan preserves record order, moves boundaries, isolates oversize, and reports call counts" q_check_plan

q_new_trace adapter
assert_ok "Q3: adapter uses the configured model and returns the stub response" \
  q_env MSEARCH_MODEL=skill-fixture-model AGENT_FLAGS=--dangerously-skip-permissions bash "$Q_AGENT" <<< 'fixture adapter check'
assert_ok "Q3: adapter accepts an explicit model" \
  q_env MSEARCH_MODEL=skill-fixture-model bash "$Q_AGENT" --model explicit-fixture-model <<< 'fixture explicit model'
assert_ok "Q3: Codex adapter works through the same stub" \
  q_env MSEARCH_MODEL=gpt-fixture AGENT_CLI=codex CODEX_FLAGS=--dangerously-skip-permissions bash "$Q_AGENT" <<< 'fixture Codex'
q_check_adapter() {
  python3 - "$Q_TRACE" <<'PY'
import json
from pathlib import Path
import sys

calls = [json.loads(path.read_text(encoding="utf-8")) for path in Path(sys.argv[1]).glob("*.json")]
by_prompt = {call["stdin"].splitlines()[-1]: call["argv"] for call in calls}
assert len(calls) == 3, calls
for prompt, model in [("fixture adapter check", "skill-fixture-model"), ("fixture explicit model", "explicit-fixture-model")]:
    argv = by_prompt[prompt]
    assert argv[argv.index("--model") + 1] == model, argv
    assert "--tools=" in argv and "--strict-mcp-config" in argv, argv
    assert "--no-session-persistence" in argv, argv
    assert "--dangerously-skip-permissions" not in argv, argv
argv = by_prompt["fixture Codex"]
assert argv[argv.index("-m") + 1] == "gpt-fixture", argv
assert argv[argv.index("-s") + 1] == "read-only", argv
assert "--dangerously-skip-permissions" not in argv, argv
PY
}
assert_ok "Q3/X14: Claude gets no tools or session persistence, Codex is read-only, and bypass flags never pass through" q_check_adapter
q_new_trace no-model
Q_NO_MODEL_STATUS=0
Q_NO_MODEL_TEXT="$(q_env MSEARCH_MODEL= AGENT_MODEL_FAST= bash "$Q_AGENT" <<< test 2>&1)" || Q_NO_MODEL_STATUS=$?
assert_eq "Q3: no fast model returns exit 2" 2 "$Q_NO_MODEL_STATUS"
assert_grep_str "Q3: no-model error identifies MSEARCH_MODEL" MSEARCH_MODEL "$Q_NO_MODEL_TEXT"
assert_grep_str "Q3: no-model error identifies AGENT_MODEL_FAST" AGENT_MODEL_FAST "$Q_NO_MODEL_TEXT"
assert_eq "Q3: no-model error does not call the CLI" 0 "$(q_trace_count)"

q_new_trace cli-override
assert_ok "Q3: MSEARCH_CLI=codex overrides AGENT_CLI=claude" \
  q_env MSEARCH_CLI=codex MSEARCH_MODEL=gpt-fixture \
    CODEX_FLAGS='--dangerously-bypass-approvals-and-sandbox --fixture-extra-flag' \
    bash "$Q_AGENT" <<< 'fixture CLI override'
q_check_cli_override() {
  python3 - "$Q_TRACE" <<'PY'
import json
from pathlib import Path
import sys

trace, = Path(sys.argv[1]).glob("*.json")
argv = json.loads(trace.read_text(encoding="utf-8"))["argv"]
assert argv[0] == "exec" and argv[argv.index("-m") + 1] == "gpt-fixture", argv
assert argv[argv.index("-s") + 1] == "read-only" and "--write" not in argv, argv
assert "--dangerously-bypass-approvals-and-sandbox" not in argv and "--fixture-extra-flag" not in argv, argv
# the child runs from an empty, non-git directory; without this flag a real
# Codex refuses to start (found by a live run, not by the stub)
assert "--skip-git-repo-check" in argv, argv
PY
}
assert_ok "Q3: the CLI override builds read-only Codex argv that can start outside a git repo, and ignores CODEX_FLAGS" q_check_cli_override
q_new_trace codex-preamble
q_check_codex_preamble() {
  q_env MSEARCH_CLI=codex MSEARCH_MODEL=gpt-fixture python3 - "$Q_AGENT" "$Q_TRACE" <<'PY'
import json
import os
from pathlib import Path
import re
import subprocess
import sys

agent, trace = sys.argv[1:]
bypass = {"AGENT_CLI_NO_PREAMBLE": "1", "AGENT_CLI_PREAMBLE": "fixture replacement", "AGENT_CLI_RECORD": "1"}
variants = [{key: value} for key, value in bypass.items()] + [bypass]
prompts = {f"fixture Codex preamble {index}": variables for index, variables in enumerate(variants)}
for prompt, variables in prompts.items():
    run = subprocess.run(["bash", agent], input=prompt, capture_output=True, text=True,
                         env=os.environ | variables)
    assert run.returncode == 0, run.stderr
    assert run.stderr.count("\n") == 1 and run.stderr.endswith("\n"), run.stderr
    assert re.search(r"Codex.*(?:connector|コネクタ)|(?:connector|コネクタ).*Codex", run.stderr, re.I), run.stderr
    assert "SKILL.md" in run.stderr, run.stderr
    echoed = json.loads(run.stdout)["echo"]
    assert "Do not use any tool" in echoed.splitlines()[0] and echoed.endswith("\n\n" + prompt), echoed
    assert "fixture replacement" not in echoed, echoed

check = subprocess.run(["bash", agent, "--check-config"], input="", capture_output=True, text=True,
                       env=os.environ | bypass)
assert check.returncode == 0 and not check.stderr, check
assert re.fullmatch(r"gpt-fixture\n[1-9][0-9]*\n", check.stdout), check.stdout
calls = [json.loads(p.read_text(encoding="utf-8")) for p in Path(trace).glob("*.json")]
assert len(calls) == len(prompts), calls
for call in calls:
    delivered = call["stdin"] or call["argv"][-1]
    assert delivered.splitlines()[-1] in prompts and "Do not use any tool" in delivered.splitlines()[0], call
    assert "--ephemeral" in call["argv"], call
PY
}
assert_ok "Y3/Z11b: Codex keeps the preamble and ephemeral mode despite environment overrides and warns on live stderr" q_check_codex_preamble

q_new_trace invalid-cli
assert_exit "Q3: an invalid MSEARCH_CLI returns exit 2" 2 \
  q_env MSEARCH_CLI=unsupported bash "$Q_AGENT" <<< 'fixture invalid CLI'
assert_eq "Q3: an invalid MSEARCH_CLI makes zero CLI calls" 0 "$(q_trace_count)"

q_new_trace baseline
assert_ok "Q4/Q6: a search with valid model responses finishes" q_search --out "$Q_ROOT/baseline"
for Q_FILE in plan.json result.json result.md run.log hits.json stats.json; do
  assert_file "Q4/Q6: search writes $Q_FILE" "$Q_ROOT/baseline/$Q_FILE"
done
q_check_records() {
  python3 - "$Q_TRACE" "$Q_INPUT/expected.json" "$Q_ROOT/baseline/plan.json" <<'PY'
from collections import Counter
import json
from pathlib import Path
import re
import sys

calls = [json.loads(path.read_text(encoding="utf-8")) for path in Path(sys.argv[1]).glob("*.json")]
expected, plan = [json.loads(Path(path).read_text(encoding="utf-8")) for path in sys.argv[2:]]
bodies = [call["stdin"].split("<records>\n", 1)[1].split("\n</records>", 1)[0]
          for call in calls if "<records>\n" in call["stdin"]]
assert all("META-SENTINEL" not in body for body in bodies), bodies
for record in expected:
    assert sum(record in body for body in bodies) == 2, record
sent = Counter(tuple(re.findall(r"(?m)^(?:\s*- id: |### )(\S+)", body)) for body in bodies)
planned = Counter(tuple(chunk["ids"]) for chunk in plan["chunks"])
assert sent == planned, (sent, planned)
assert all(call["argv"][call["argv"].index("--model") + 1] == "fast-fixture-model" for call in calls), calls
assert all(not call["cwd_entries"] for call in calls), calls
PY
}
assert_ok "Q2/Q3: the adapter receives each complete record in its planned chunk, from an empty working directory" q_check_records

q_check_temporary_agent_cwd() {
  python3 - "$Q_TRACE" "$Q_TMP" "$Q_ROOT/baseline" <<'PY'
import json
from pathlib import Path
import sys

trace, temporary, output = map(Path, sys.argv[1:])
working_dirs = {Path(json.loads(path.read_text(encoding="utf-8"))["cwd"]) for path in trace.glob("*.json")}
assert working_dirs, "no calls recorded"
assert all(path.parent == temporary and not path.is_relative_to(output) for path in working_dirs), working_dirs
assert not any(path.exists() for path in working_dirs), working_dirs
PY
}
assert_ok "Z2: the child starts outside the output tree in a temporary folder that is removed" q_check_temporary_agent_cwd

q_check_filtering() {
  python3 - "$Q_ROOT/baseline/result.json" <<'PY'
import json
from pathlib import Path
import sys

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
counts = data["counts"]
assert data["status"] == "COMPLETE", data["status"]
assert {record["id"] for record in data["records"]} == {f"F-{n:03}" for n in [*range(1, 9), 11]}, data["records"]
assert counts["invented_ids_dropped"] == 4, counts
assert counts["unverified_quotes_dropped"] == counts["invalid_passages_dropped"] == 4, counts
assert all(
    Path(excerpt["file"]).read_text(encoding="utf-8").splitlines()[quote["line"] - 1] == quote["text"]
    for excerpt in data["excerpts"]
    for quote in excerpt["quotes"]
), data["excerpts"]
assert any(quote["text"] == "  original  spacing"
           for excerpt in data["excerpts"] for quote in excerpt["quotes"]), data["excerpts"]
by_id = {}
for excerpt in data["excerpts"]:
    by_id.setdefault(excerpt["record_id"], set()).update(quote["line"] for quote in excerpt["quotes"])
assert by_id == {"F-001": {3}, "F-002": {3}, "F-004": {3}, "F-008": {2}, "F-011": {5}}, by_id
PY
}
assert_ok "Q4/X19: invented IDs and invalid passages are dropped and each record has exactly its verified quote lines" q_check_filtering

q_check_passes_and_windows() {
  python3 - "$Q_ROOT/baseline/result.json" <<'PY'
import json
from pathlib import Path
import sys

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
records = {record["id"]: record for record in data["records"]}
for record_id, strength, expected_passes in [
    ("F-001", "直接", {"preread:p1", "preread:p2"}), ("F-002", "直接", {"preread:p1"}),
    ("F-003", "直接", {"preread:p2"}), ("F-004", "関連", {"preread:p1", "preread:p2"}),
]:
    record = records[record_id]
    assert record["strength"] == strength and record["why"] == f"fixture reason {strength}", record
    assert set(record["routes"]) - {"source"} == expected_passes, record
notes_windows = [window for chunk in data["chunks"] for window in chunk.get("snippets", [])
                 if Path(window["file"]).name == "notes.txt"]
window, = notes_windows
assert (window["line_from"], window["line_to"]) == (2, 5), window
PY
}
assert_ok "X20: distinct passes contribute hits, stronger responses win in either order, and overlapping windows merge" q_check_passes_and_windows

q_check_sources() {
  python3 - "$Q_ROOT/baseline/result.json" "$Q_TRACE" <<'PY'
import json
from pathlib import Path
import sys

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
sources = {r["id"]: r["source"] for r in data["records"]}
for record_id, file in {
    "F-001": "notes.txt", "F-002": "meeting-2026-01-12.txt",
    "F-004": "meeting-2026-01-13-b.txt", "F-008": "unclocked.txt"
}.items():
    source = sources[record_id]
    assert source["state"] == "resolved" and Path(source["file"]).name == file, source
    if record_id != "F-008":
        assert (source["line_from"], source["line_to"]) == (2, 4), source
for record_id in ("F-003", "F-005", "F-006"):
    source = sources[record_id]
    assert source["state"] == "unresolved" and source["why"], source
assert sources["F-007"]["state"] == "missing", sources["F-007"]
assert data["counts"]["unresolved_sources"] == 4, data["counts"]
calls = [json.loads(path.read_text(encoding="utf-8")) for path in Path(sys.argv[2]).glob("*.json")]
assert any('file="unclocked.txt" lines="L1-L5"' in call["stdin"]
           and "L1|beginning" in call["stdin"] and "L5|last line" in call["stdin"] for call in calls), calls
PY
}
assert_ok "Q6: path, unique date, explicit meeting, ambiguity, mail, unsupported and missing sources resolve as specified" q_check_sources

q_check_default_grep() {
  python3 - "$Q_TRACE" <<'PY'
import json
from pathlib import Path
import sys

calls = [json.loads(path.read_text(encoding="utf-8")) for path in Path(sys.argv[1]).glob("*.json")]
assert calls and not any("論点の言い換え・関係語・聞き違いの語を出す" in call["stdin"] for call in calls)
PY
}
assert_ok "Q10: default search never calls the term expander" q_check_default_grep
q_new_trace expand
assert_ok "Q10: --expand-grep completes through the same adapter" \
  q_search --out "$Q_ROOT/expand" --expand-grep --skip-verbatim
q_check_expanded_grep() {
  python3 - "$Q_TRACE" "$Q_ROOT/expand/result.json" <<'PY'
import json
from pathlib import Path
import sys

calls = [json.loads(path.read_text(encoding="utf-8")) for path in Path(sys.argv[1]).glob("*.json")]
assert sum("論点の言い換え・関係語・聞き違いの語を出す" in call["stdin"] for call in calls) == 1
data = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
record = next(record for record in data["records"] if record["id"] == "F-009")
assert record["routes"] == ["grep"] and record["grep_terms"] == ["青箱点検"], record
PY
}
assert_ok "Q10: expanding terms yields a grep-only hit with its matching term" q_check_expanded_grep

q_new_trace grep-judge
assert_ok "X20: growth beyond the grep threshold triggers readback" \
  q_search --out "$Q_ROOT/grep-judge" --expand-grep --grep-direct-max 1 --skip-verbatim
q_check_grep_judgment() {
  python3 - "$Q_ROOT/grep-judge" <<'PY'
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
result = json.loads((root / "result.json").read_text(encoding="utf-8"))
grep = json.loads((root / "hits.json").read_text(encoding="utf-8"))["grep"]
terms = {item["term"]: item for item in grep["terms"]}
assert terms["record boundary marker"]["dropped"] == "一般的すぎる", terms
assert grep["grep_only_candidates"] == 2 and grep["judged_in"] == grep["judged_out"] == 1, grep
assert grep["rejected_ids"] == ["F-010"], grep
chunk, = [chunk for chunk in result["chunks"] if chunk["name"].startswith("grepjudge-")]
assert chunk["state"] == "OK" and chunk["ids"] == ["F-009", "F-010"], chunk
records = {r["id"]: r for r in result["records"]}
kept = records["F-009"]
assert kept["routes"] == ["grep"] and kept["grep_terms"] == ["青箱点検"] and kept["strength"] == "関連", kept
assert "F-010" not in records and all("record boundary marker" not in r.get("grep_terms", []) for r in records.values())
PY
}
assert_ok "X20: grep discards generic terms and model judgment accepts one candidate and rejects another" q_check_grep_judgment

Q_RULES="$Q_ROOT/fail-first.json"
printf '%s\n' '{"hits":["F-001"],"fail_first":"F-001"}' > "$Q_RULES"
q_new_trace fail-first
assert_exit "Q5: a failed first-pass chunk returns exit 3 even when pass two recovers the hit" 3 \
  q_search --out "$Q_ROOT/fail-first" --parallel 1 --skip-verbatim
q_check_failed_pass() {
  python3 - "$Q_ROOT/fail-first/result.json" "$Q_ROOT/fail-first/result.md" <<'PY'
import json
from pathlib import Path
import sys

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
report = Path(sys.argv[2]).read_text(encoding="utf-8")
failed = [chunk for chunk in data["chunks"] if chunk["state"] == "FAILED"]
assert data["status"] == "PARTIAL" and data["counts"]["failed_chunks"] == len(failed) == 1, data
chunk = failed[0]
assert chunk["pass"] == 1 and "F-001" in chunk["ids"] and chunk["error"], chunk
scope = report.split("\n## 見た範囲\n", 1)[1].split("\n## ", 1)[0]
span = f"（{chunk['ids'][0]}〜{chunk['ids'][-1]}）"
assert f"- **FAILED {chunk['name']}**{span}：{chunk['error']}" in scope.splitlines(), scope
record = next(record for record in data["records"] if record["id"] == "F-001")
assert "preread:p1" not in record["routes"] and "preread:p2" in record["routes"], record
PY
}
assert_ok "Q5/X19: the report scope names the failed chunk and its ID span alongside the recovered record" q_check_failed_pass

Q_RULES="$Q_ROOT/malformed.json"
printf '%s\n' '{"invalid_json":"F-001"}' > "$Q_RULES"
q_new_trace malformed
assert_exit "Q5: malformed JSON is retried and then exits 3" 3 \
  q_search --out "$Q_ROOT/malformed" --only 1 --passes 1 --retries 1 --skip-verbatim
assert_eq "Q5: the malformed chunk was called twice" 2 "$(q_trace_count)"
q_check_malformed() {
  python3 - "$Q_ROOT/malformed/result.json" <<'PY'
import json
from pathlib import Path
import sys

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert data["status"] == "PARTIAL" and data["counts"]["failed_chunks"] == 1, data
chunk, = data["chunks"]
assert chunk["state"] == "FAILED" and chunk["error"], chunk
PY
}
assert_ok "Q5: exhausted JSON retry is recorded as a failed chunk" q_check_malformed

q_new_trace output
assert_exit "Q7: --out pointing into the skill is refused" 2 q_search --out "$Q_SKILL/bad-output"
assert_exit "Q7: --out pointing at the input directory is refused" 2 q_search --out "$Q_INPUT"
assert_absent "Q7: a refused output path is untouched" "$Q_SKILL/bad-output"
assert_ok "Q7: default output with no MSEARCH_OUT_DIR succeeds" q_search --dry-run
assert_eq "Q7: default output creates one plan under TMPDIR" 1 "$(find "$Q_TMP" -type f -name plan.json | wc -l)"
assert_eq "Q7: the full input fixture stays byte-identical" "$Q_BEFORE" "$(tree_hashes "$Q_INPUT")"
assert_eq "Q7: the mishearing template has zero data rows" 0 \
  "$(sed '/<!--/,/-->/d' "$Q_SKILL/mishearings.md.example" |
    awk '/^\|/ && !/^\|---/ && !/^\| 逐語の語/ { rows++ } END { print rows+0 }')"

cat > "$Q_ROOT/sample-expected.json" <<'SAMPLE_EXPECTED'
{
  "人員が異動するときの引き継ぎ": {
    "records": ["F-003", "F-004", "K-001", "D-2026-01-15-01"],
    "quotes": {
      "2026-01-15_handoff.txt": {"3": "検品責任者も引き継いでください", "4": "後任と現場を一周します", "6": "私が後任に例外処理を見せます"}
    }
  },
  "在庫履歴の保存期間と監査への影響": {
    "records": ["F-005", "H-001", "D-2026-01-16-01"],
    "quotes": {
      "2026-01-15_handoff.txt": {"7": "保存機関は今のところ12か月です", "8": "12か月では足りないかもしれません"},
      "2026-01-16_operations.txt": {"6": "過去何か月分の在庫表を遡るか"}
    }
  }
}
SAMPLE_EXPECTED

Q_SAMPLE_TOPICS="$(python3 - "$Q_ROOT" <<'PY'
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
expected = json.loads((root / "sample-expected.json").read_text(encoding="utf-8"))
for index, (topic, expectation) in enumerate(expected.items(), 1):
    rules = {"hits": expectation["records"],
             "quote_lines": {file: list(map(int, lines)) for file, lines in expectation["quotes"].items()}}
    (root / f"sample-rules-{index}.json").write_text(json.dumps(rules), encoding="utf-8")
    print(topic)
PY
)"
Q_SAMPLE_INDEX=0
while IFS= read -r Q_SAMPLE_TOPIC; do
  Q_SAMPLE_INDEX=$((Q_SAMPLE_INDEX + 1))
  Q_RULES="$Q_ROOT/sample-rules-$Q_SAMPLE_INDEX.json"
  q_new_trace "sample-$Q_SAMPLE_INDEX"
  assert_ok "Q7/X21: sample topic $Q_SAMPLE_INDEX runs through the adapter with the shipped sample inputs" \
    q_env python3 "$Q_SEARCH" --topic "$Q_SAMPLE_TOPIC" --ledger "$Q_SAMPLE/ledger.yaml" \
      --journal "$Q_SAMPLE/decisions_journal.md" --glossary "$Q_SAMPLE/glossary.md" \
      --mishearings "$Q_SAMPLE/mishearings.md" --transcripts "$Q_SAMPLE/transcripts" --source-root "$Q_SAMPLE" \
      --pad 1 --retries 0 --out "$Q_ROOT/sample-$Q_SAMPLE_INDEX"
done <<< "$Q_SAMPLE_TOPICS"

q_check_sample() {
  python3 - "$Q_SAMPLE" "$Q_ROOT" <<'PY'
import json
from pathlib import Path
import re
import sys

sample, root = map(Path, sys.argv[1:])
key = json.loads((sample / "answer_key.json").read_text(encoding="utf-8"))["topics"]
expected = json.loads((root / "sample-expected.json").read_text(encoding="utf-8"))
assert key.keys() == expected.keys(), key.keys()
materials = {sample / name: (sample / name).read_text(encoding="utf-8").splitlines()
             for name in ("ledger.yaml", "decisions_journal.md")}
for index, (topic, expectation) in enumerate(expected.items(), 1):
    result = json.loads((root / f"sample-{index}/result.json").read_text(encoding="utf-8"))
    assert result["topic"] == topic and result["status"] == "COMPLETE", result
    expected_ids = set(expectation["records"])
    assert set(key[topic]["records"]) == expected_ids == {record["id"] for record in result["records"]}
    for record in result["records"]:
        line = materials[Path(record["file"])][record["line"] - 1]
        assert re.match(rf"^(?:\s*- id: |### ){re.escape(record['id'])}(?:\s|$)", line), (record, line)
    expected_quotes = {}
    for file, lines in expectation["quotes"].items():
        path = sample / "transcripts" / file
        transcript = path.read_text(encoding="utf-8").splitlines()
        for number, marker in lines.items():
            number = int(number)
            text = transcript[number - 1]
            assert marker in text, (file, number, text)
            expected_quotes[path, number] = text
    assert {(sample / quote["file"], quote["line"]) for quote in key[topic]["quotes"]} == expected_quotes.keys()
    actual_quotes = set()
    for excerpt in result["excerpts"]:
        for quote in excerpt["quotes"]:
            actual_quotes.add((Path(excerpt["file"]), quote["line"], quote["text"]))
    assert actual_quotes == {(file, line, text) for (file, line), text in expected_quotes.items()}, actual_quotes
PY
}
assert_ok "Q8/X21: both sample topics match all expected IDs and quote lines at their original source locations" q_check_sample

python3 - "$Q_SAMPLE" "$Q_ROOT" <<'PY'
import json
from pathlib import Path
import sys

sample, root = map(Path, sys.argv[1:])
full_path = root / "sample-1/result.json"
result = json.loads(full_path.read_text(encoding="utf-8"))
result["records"] = [record for record in result["records"] if record["id"] != "F-003"]
for excerpt in result["excerpts"]:
    excerpt["quotes"] = [quote for quote in excerpt["quotes"] if quote["line"] != 3]
(root / "score-partial.json").write_text(json.dumps(result), encoding="utf-8")

result = json.loads(full_path.read_text(encoding="utf-8"))
twin_root = root / "other-project/transcripts"
twin_root.mkdir(parents=True)
for excerpt in result["excerpts"]:
    original = Path(excerpt["file"])
    twin = twin_root / original.name
    twin.write_bytes(original.read_bytes())
    excerpt["file"] = str(twin)
(root / "score-wrong-file.json").write_text(json.dumps(result), encoding="utf-8")
PY

Q_SCORE_FULL="$(python3 "$Q_SCORE" "$Q_ROOT/sample-1/result.json" "$Q_SAMPLE/answer_key.json")"
Q_SCORE_PARTIAL="$(python3 "$Q_SCORE" "$Q_ROOT/score-partial.json" "$Q_SAMPLE/answer_key.json")"
Q_SCORE_WRONG_FILE="$(python3 "$Q_SCORE" "$Q_ROOT/score-wrong-file.json" "$Q_SAMPLE/answer_key.json")"
assert_grep_str "Q8: full score reports 100% of record IDs" 'records recall: 4/4 (100.0%)' "$Q_SCORE_FULL"
assert_grep_str "Q8: full score reports 100% of quoted lines" 'quotes recall: 3/3 (100.0%)' "$Q_SCORE_FULL"
assert_grep_str "Q8: one missed ID lowers recall" 'records recall: 3/4 (75.0%)' "$Q_SCORE_PARTIAL"
assert_grep_str "Q8: score names the missed ID" 'missed ids: F-003' "$Q_SCORE_PARTIAL"
assert_grep_str "Q8: score names the missed quote" 'missed quotes: transcripts/2026-01-15_handoff.txt:3' "$Q_SCORE_PARTIAL"
assert_grep_str "X18: a different directory with the same file name, lines, and text scores zero quotes" \
  'quotes recall: 0/3 (0.0%)' "$Q_SCORE_WRONG_FILE"
assert_grep_str "X22: K-001 asks about including the deputy in addition to the successor" \
  '"K-001": "後任に加えて副担当にも渡すか' "$(cat "$Q_SAMPLE/answer_key.json")"

assert_eq "Q7/X21: sample files stay byte-identical after searching both topics" "$Q_SAMPLE_BEFORE" "$(tree_hashes "$Q_SAMPLE")"

# X1–X3, X5–X6, X8–X10. Ledger parsing, source resolution and input paths.
q_check_source_review() {
  python3 -B - "$Q_SEARCH" "$Q_ROOT/source-reviews" "$1" <<'PY'
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace

script, root, check = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), sys.argv[3]
work = root / check
kit = work / "kit"
kit.mkdir(parents=True)
os.environ["MSEARCH_KIT_ROOT"] = str(kit)
spec = importlib.util.spec_from_file_location("meaning_search", script)
ms = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ms)

allowed = work / "allowed"
ledger = allowed / "ledgers" / "ledger.yaml"
journal = allowed / "journal.md"
transcripts = allowed / "transcripts"
mail = allowed / "mail"
for directory in (ledger.parent, transcripts, mail):
    directory.mkdir(parents=True)
ledger.write_text("facts:\n- id: F-BASE\n", encoding="utf-8")

def inputs(**changes):
    options = dict(project=None, ledger=[ledger], source_root=[], journal=None, glossary=None,
                   mishearings=None, transcripts=transcripts, mail_dir=mail, meeting=[])
    args = SimpleNamespace(**(options | changes))
    ms.prepare_inputs(args)
    return args

def record(source, *, section="facts", text="", fresh=""):
    return SimpleNamespace(source=source, section=section, file=journal if section == "journal" else ledger,
                           fresh=fresh, text=text)

def run(*flags, cwd=work):
    return subprocess.run([sys.executable, "-B", str(script), "--topic", "fixture", "--dry-run", *flags],
                          cwd=cwd, text=True, capture_output=True, check=False)

def transcript(name, *, times=False, directory=transcripts):
    path = directory / name
    lines = [f"[00:00:{n:02}] fixture line {n}" if times else f"fixture line {n}" for n in range(1, 51)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path

if check == "X1":
    ledger.write_text("""meta:
  skip: yes
facts:
  - id: F-FIRST
    note: |
      - id: F-NOTE
    options:
      - id: F-OPTION
  - id: F-SECOND
holes:
- id: H-FIRST
  options:
    - id: H-OPTION
""", encoding="utf-8")
    for name, flags, expected in (
        ("default", [], ["F-FIRST", "F-SECOND", "H-FIRST"]),
        ("custom", ["--record-re", r"^\s*- id:\s*(\S+)"],
         ["F-FIRST", "F-NOTE", "F-OPTION", "F-SECOND", "H-FIRST", "H-OPTION"]),
    ):
        output = work / name
        proc = run("--ledger", str(ledger), "--passes", "1", "--out", str(output), *flags)
        assert proc.returncode == 0, proc.stderr
        plan = json.loads((output / "plan.json").read_text(encoding="utf-8"))
        assert [hid for chunk in plan["chunks"] for hid in chunk["ids"]] == expected, plan
    first = ms.parse_entries(ledger, None)[0].text
    assert "- id: F-NOTE" in first and "- id: F-OPTION" in first, first

elif check == "X2":
    meeting = transcript("meeting.txt", times=True)
    args = inputs()
    for missing in ("meeting-final", "meeting.txt"):
        ws, meetings, whole, issue = ms.resolve_refs(record(f"talk:{missing}@00:00:35"), args)
        assert (ws, meetings, whole) == ([], [], []) and issue, (ws, meetings, whole, issue)
    assert ms.resolve_refs(record("talk:meeting@00:00:35"), args) == ([(meeting, 35, 35)], [], [], "")

elif check == "X3":
    first = work / "root-1"
    second = work / "root-2"
    for directory in (first, second):
        directory.mkdir()
    one, two = (transcript("notes.txt", directory=directory) for directory in (first, second))
    same = transcript("same.txt", directory=first)
    (second / same.name).symlink_to(same)
    same_day_one = transcript("2026-01-13_会議_L42.txt")
    same_day_two = transcript("2026-01-13_tech.txt")
    transcript("会議.txt")
    transcript("L42.txt")
    args = inputs(source_root=[first, second])
    ws, _, _, issue = ms.resolve_refs(record("notes.txt:2"), args)
    assert not ws and str(one) in issue and str(two) in issue, (ws, issue)
    assert ms.resolve_refs(record("same.txt:2"), args) == ([(same, 2, 2)], [], [], "")
    for text in ("2026-01-13 会議", "2026-01-13 L42", "2026-01-13 会議 L42"):
        ws, meetings, whole, issue = ms.resolve_refs(record(text), args)
        assert (ws, meetings, whole) == ([], [], []), (text, ws, meetings, whole)
        assert same_day_one.name in issue and same_day_two.name in issue, (text, issue)
    assert ms.resolve_refs(record("2026-01-13 tech"), args) == ([], [same_day_two], [], "")

elif check == "X5":
    outside = work / "outside"
    outside.mkdir()
    external = transcript("outside.txt", times=True, directory=outside)
    (allowed / "escaped.txt").symlink_to(external)
    alias = transcripts / "escaped-talk.txt"
    alias.symlink_to(external)
    (transcripts / "2026-01-13-escaped.txt").symlink_to(external)
    transcript("2026-01-13-safe.txt", times=True)
    (mail / "2026-01-13.txt").symlink_to(external)
    transcript("2026-01-13-safe.txt", directory=mail)
    args = inputs(source_root=[allowed])
    original_read = ms.read_physical_lines

    def guard_read(path):
        assert path.resolve() != external, path
        return original_read(path)

    ms.read_physical_lines = guard_read
    for source in (f"{external}:3", "../outside/outside.txt:3", "escaped.txt:3",
                   "talk:escaped-talk@00:00:03", "talk:00:00:03",
                   "mail:2026-01-13", "escaped-talk L3"):
        ws, meetings, whole, issue = ms.resolve_refs(record(source, fresh="2026-01-13"), args)
        assert (ws, meetings, whole) == ([], [], []) and "根の外" in issue, (source, issue)
    args = inputs(source_root=[allowed, outside], meeting=[str(external)])
    ms.read_physical_lines = original_read
    assert args.meeting_files == [external], args.meeting_files
    assert ms.resolve_refs(record(f"{external}:3"), args) == ([(external, 3, 3)], [], [], "")

elif check == "X6":
    output = work / "output"
    output.mkdir()
    alias = output / "run.log"
    alias.symlink_to(ledger)
    alias_dir = work / "alias-dir"
    alias_dir.symlink_to(output, target_is_directory=True)
    before = ledger.read_bytes()
    for input_path in ("../output/run.log", "../alias-dir/run.log"):
        proc = run("--ledger", input_path, "--out", "../output", cwd=allowed)
        assert proc.returncode == 2 and "入力のフォルダ" in proc.stderr, (proc.returncode, proc.stderr)
    assert alias.is_symlink() and alias.resolve() == ledger and ledger.read_bytes() == before
    assert list(output.iterdir()) == [alias], list(output.iterdir())

elif check == "X8":
    file = transcript("fixture-status.txt", times=True)
    ledger.write_text("""facts:
- id: F-FOLDED
  source: >
    talk:fixture-status@00:00:03
  fresh: 2026-01-13
- id: F-MULTILINE
  source: status
    L42
  fresh: 2026-01-14
""", encoding="utf-8")
    entries = ms.parse_entries(ledger, re.compile(r"^- id:\s*(\S+)"))
    assert [(e.source, e.fresh) for e in entries] == [
        ("talk:fixture-status@00:00:03", "2026-01-13"),
        ("status L42", "2026-01-14"),
    ], [(e.source, e.fresh) for e in entries]
    args = inputs()
    assert [ms.resolve_refs(e, args)[0] for e in entries] == [[(file, 3, 3)], [(file, 42, 42)]]

elif check == "X9":
    first = transcript("会議A.txt")
    second = transcript("会議B.txt")
    partial = transcript("weekly-status-followup.txt")
    args = inputs()
    entry = record("", section="journal", text="会議A L12、会議B L34。別の話 L50")
    assert ms.resolve_refs(entry, args) == ([(first, 12, 12), (second, 34, 34)], [], [], "")
    entry = record("", section="journal", text="会議A。別の話 L50")
    assert ms.resolve_refs(entry, args) == ([], [first], [], "")
    entry = record("", section="journal", text="status L42")
    assert ms.resolve_refs(entry, args) == ([(partial, 42, 42)], [], [], "")

elif check == "X10":
    file = transcript("status.txt")
    ws, meetings, whole, issue = ms.resolve_refs(record("status L3、L5-L51、L999"), inputs())
    assert (ws, meetings, whole) == ([(file, 3, 3), (file, 5, 50)], [], []), (ws, meetings, whole)
    assert "L5–L51" in issue and "L999" in issue, issue

elif check == "Y6d":
    alias = work / "input-alias"
    alias.symlink_to(ledger.parent, target_is_directory=True)
    before = ledger.read_bytes()
    for output in (str(alias), str(ledger.parent / ".." / "ledgers"), "."):
        proc = run("--ledger", str(ledger), "--out", output, cwd=ledger.parent)
        assert proc.returncode == 2 and "入力のフォルダ" in proc.stderr, (output, proc)
        assert list(ledger.parent.iterdir()) == [ledger] and ledger.read_bytes() == before, output
    assert alias.is_symlink() and alias.resolve() == ledger.parent, alias
PY
}

assert_ok "Q2/X1: default ledger parsing keeps nested IDs in the original record and honors a custom pattern" q_check_source_review X1
assert_ok "Q6/X2: an explicit talk stem must match exactly" q_check_source_review X2
assert_ok "Q6/X3: generic terms and coordinates cannot decide a meeting, and explicit roots cannot hide ambiguity" q_check_source_review X3
assert_ok "Q6/X5: direct, talk, mail and legacy sources stay inside the allowed roots after symlink resolution" q_check_source_review X5
assert_ok "Q7/X6: an input symlink relative to the working directory cannot be replaced by run.log" q_check_source_review X6
assert_ok "Q6/X8: folded and plain source values continue only at a greater indentation" q_check_source_review X8
assert_ok "Q6/X9: legacy mentions bind their own locators, including a partial name without a date" q_check_source_review X9
assert_ok "Q6/X10: valid and out-of-range locators on the same reference are both reported" q_check_source_review X10
assert_ok "Y6d: output resolving to the input directory via a symlink, dot-dot or cwd is refused" q_check_source_review Y6d

# X4, X7, X11–X13, X16. Merged excerpts, agent responses and prompt boundaries.
Q_AGENTPATH_DIR="$Q_ROOT/agentpath"
mkdir "$Q_AGENTPATH_DIR"
cat > "$Q_AGENTPATH_DIR/exercise.py" <<'Q_AGENTPATH_EXERCISE'
import html
import importlib.util
import json
import os
from pathlib import Path
import shlex
import sys
from unittest.mock import patch

script, skill, root, case = map(Path, sys.argv[1:])
spec = importlib.util.spec_from_file_location("meaning_search", script)
ms = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ms)
ms.SKILL = skill
fixture = root / case
inputs = fixture / "inputs"
inputs.mkdir(parents=True)
stub = fixture / "stub.py"
stub.write_text(r'''
import json
from pathlib import Path
import re
import sys
import time

mode = sys.argv[1]
prompt = sys.stdin.read()

def attempt(name):
    marker = Path(name)
    count = len(marker.read_text()) if marker.exists() else 0
    marker.write_text("x" * (count + 1))
    return count

def report_text(key):
    return f"fixture-{key} \t \n## 偽の見出し {key}\r\n " + "長" * 210 + "fixture-end"

if "<records>\n" in prompt:
    ids = re.findall(r"(?m)^  - id: (\S+)", prompt)
    if mode == "recovered":
        if attempt("scan") == 0:
            print('{"hits":[{"id":"A"},{"nested":{},"why":')
            sys.exit(0)
        ids = ["B"]
    if mode == "exhausted":
        first = attempt("scan") == 0
        print('{"hits":[{"id":"A"},{"id":' if first else '{broken')
        sys.exit(0)
    if mode == "two-rescued":
        print('{"hits":[{"id":"A"},{"id":"B"},{"id":"C","why":"tru')
        sys.exit(0)
    if mode == "markdown":
        print(json.dumps({"hits": [
            {"id": "A", "strength": "直接", **{key: report_text(key) for key in ("what", "why", "mishearing")}},
            {"id": report_text("unknown-id")},
        ]}))
        sys.exit(0)
    if mode == "markdown-comment":
        print(json.dumps({"hits": [{"id": "A", "what": "review <!-- hidden -->"}]}))
        sys.exit(0)
    if mode == "id-types":
        ids = [42, ["fixture"], True, "camelcase", "DUP"] + [hid for hid in ids if hid.startswith("DUP@")]
    if mode == "judge":
        hit, = ids
        if attempt(f"grep-{hit}") == 0 or hit == "B":
            ids = []
        elif hit == "C":
            sys.exit(8)
    if mode == "timeout":
        time.sleep(2)
    print(json.dumps({"hits": [{"id": hit, "strength": "直接"} for hit in ids]}))
elif "<snippets>\n" in prompt:
    ids = re.findall(r'<snippet id="([^"]+)"', prompt)
    rows = [{"snippet": sid, "relevant": False, "passages": []} for sid in ids]
    if mode == "shape":
        alternatives = [
            [], [{"snippet": ids[0]}], [{**rows[0], "relevant": "false"}],
            [{**rows[0], "passages": {}}], rows * 2, [{**rows[0], "snippet": "invented"}], rows,
        ]
        rows = alternatives[attempt("shape")]
    if mode == "markdown":
        rows[0].update(relevant=True, summary=report_text("summary"), passages=[
            {"lines": [1, 1], "says": report_text("says"), "mishearing": report_text("passage-mishearing")},
        ])
    if mode == "snippet-keys" or mode == "line-types":
        for row, name in zip(rows, re.findall(r'<snippet id="[^"]+" file="([^"]+)"', prompt)):
            if mode == "snippet-keys":
                row.update(relevant=name == "yes.txt", failed=True, summary=f"summary for {name}",
                           unexpected="fixture-unknown-key-value", passages=[{"lines": [1, 1]}])
            else:
                spans = [[3, 3], [True, True], ["2", "2"]] if name == "type.txt" else [[3, 3], [2, 2], [6, 6]]
                row.update(relevant=True, passages=[{"lines": span} for span in spans])
    if mode == "merge" and 'file="failed.txt"' in prompt:
        sys.exit(8)
    if mode == "escape" or (mode == "merge" and 'file="notes.txt"' in prompt):
        quote = 1 if mode == "escape" else 8
        rows[0].update(relevant=True, passages=[{"lines": [quote, quote]}])
    print(json.dumps({"snippets": rows}))
else:
    print(json.dumps({"terms": [{"term": "judge-fixture"}]}))
''', encoding="utf-8")


def write(name, content):
    path = inputs / name
    path.write_text(content, encoding="utf-8")
    return path


def search(mode, records, *options, retries=0):
    ledger = write(f"{mode}.yaml", "facts:\n" + "".join(
        f"  - id: {record_id}\n    {body}\n" for record_id, body in records
    ))
    out = fixture / mode
    command = shlex.join([sys.executable, str(stub), mode])
    argv = [str(script), "--topic", "fixture", "--ledger", str(ledger), "--source-root", str(inputs),
            "--out", str(out), "--agent", command, "--passes", "1", "--parallel", "1",
            "--retries", str(retries), *options]
    ms.STATS = {"calls": 0, "retries": 0, "failures": 0, "call_secs": 0.0, "by_kind": {}}
    # Skip the retry delay only in the parent. The agent stub runs unmodified in a subprocess.
    with patch.object(sys, "argv", argv), patch.object(ms.time, "sleep"):
        status = ms.main()
    return status, json.loads((out / "result.json").read_text(encoding="utf-8")), out


if case.name == "x4":
    for name in ("notes.txt", "failed.txt", "empty.txt"):
        write(name, "\n".join(f"original line {n}" for n in range(1, 11)))
    status, data, out = search("merge", [("A", "source: notes.txt:3"), ("B", "source: notes.txt:7"),
                                        ("C", "source: failed.txt:3"), ("D", "source: empty.txt:3")],
                               "--pad", "2", "--max-verbatim-tokens", "70")
    assert status == 3 and data["status"] == "PARTIAL", data
    excerpts = {item["record_id"]: (item["line_from"], item["line_to"], [q["line"] for q in item["quotes"]])
                for item in data["excerpts"]}
    assert excerpts == {"A": (1, 5, []), "B": (5, 9, [8]), "D": (1, 5, [])}, excerpts
    assert {r["id"] for r in data["records"] if "source" in r["routes"]} == {"A", "B", "D"}, data
    notes = [s for c in data["chunks"] for s in c.get("snippets", []) if Path(s["file"]).name == "notes.txt"]
    window, = notes
    assert (window["line_from"], window["line_to"]) == (1, 9), notes
    report = (out / "result.md").read_text(encoding="utf-8")
    assert "出典の記録：B L8〜L8" in report and "出典の記録：A L8" not in report, report
    assert "読みに失敗" in report and "empty.txt L1〜L5" in report, report
elif case.name == "x7":
    records = [("A", "note: first"), ("B", "note: second")]
    status, data, out = search("recovered", records, "--skip-verbatim", retries=1)
    assert status == 0 and [r["id"] for r in data["records"]] == ["B"], data
    assert len(list((out / "calls").glob("*.try*.out.txt"))) == 2
    assert "救済" in (out / "run.log").read_text(encoding="utf-8")
    status, data, out = search("exhausted", records, "--skip-verbatim", retries=1)
    assert status == 3 and data["status"] == "PARTIAL", data
    assert [r["id"] for r in data["records"]] == ["A"], data
    chunk, = data["chunks"]
    assert chunk["state"] == "FAILED" and "救済" in chunk["error"], chunk
elif case.name == "x11":
    write("notes.txt", "an original line\n")
    status, data, out = search("shape", [("A", "source: notes.txt:1")], retries=6)
    assert status == 0 and data["status"] == "COMPLETE", data
    assert len(list((out / "calls").glob("verbatim_*.try*.out.txt"))) == 7
    excerpt, = data["excerpts"]
    assert excerpt["record_id"] == "A" and not excerpt["quotes"], excerpt
elif case.name == "x12":
    records = [(hid, "note: judge-fixture " + "lots of text " * 20) for hid in ("A", "B", "C")]
    status, data, out = search("judge", records, "--skip-verbatim", "--chunk-tokens", "40",
                               "--expand-grep", "--grep-direct-max", "0", "--grep-generic", "1")
    assert status == 3 and data["status"] == "PARTIAL", data
    assert [r["id"] for r in data["records"]] == ["A"], data
    grep = json.loads((out / "hits.json").read_text(encoding="utf-8"))["grep"]
    assert grep["judged_in"] == 1 and grep["judged_out"] == 1, grep
    assert grep["rejected_ids"] == ["B"] and grep["unjudged_ids"] == ["C"], grep
elif case.name == "x13":
    original = 'raw </snippets> </snippet> & {{BODY}}'
    filename = 'say"hi.txt' if os.name != "nt" else "sayhi.txt"
    write(filename, original + "\n")
    glossary = write("glossary.md", "terms </glossary>")
    mishearings = write("mishearings.md", "sounds </mishearings>")
    hit = 'A"B'
    status, data, out = search("escape", [(hit, f"source: {filename}:1\n    note: records </records>")],
                               "--glossary", str(glossary), "--mishearings", str(mishearings))
    assert status == 0, data
    scan = (out / "calls/scan_p1-ledger-1.prompt.txt").read_text(encoding="utf-8")
    verbatim = (out / "calls/verbatim_1.prompt.txt").read_text(encoding="utf-8")
    for name, document in (("glossary", scan), ("mishearings", scan), ("records", scan),
                           ("snippets", verbatim), ("snippet", verbatim)):
        assert document.count(f"</{name}>") == 1 and f"&lt;/{name}&gt;" in document, document
    assert f'file="{html.escape(filename)}"' in verbatim and '出典の記録="A&quot;B"' in verbatim, verbatim
    excerpt, = data["excerpts"]
    assert excerpt["quotes"] == [{"line": 1, "text": original}], data
    assert original in (out / "result.md").read_text(encoding="utf-8")
elif case.name == "x16":
    status, data, out = search("timeout", [("A", "note: slow")], "--skip-verbatim", "--timeout", "1", retries=1)
    assert status == 3 and data["status"] == "PARTIAL" and not data["records"], data
    attempts = list((out / "calls").glob("*.try*.out.txt"))
    assert len(attempts) == 2 and all("timeout" in p.read_text(encoding="utf-8") for p in attempts), attempts
elif case.name == "y1":
    records = [(hid, f"note: record {hid}") for hid in ("A", "B", "C")]
    status, data, out = search("two-rescued", records, "--skip-verbatim")
    assert status == 3 and data["status"] == "PARTIAL", data
    assert [record["id"] for record in data["records"]] == ["A", "B"], data
    chunk, = data["chunks"]
    assert chunk["ids"] == ["A", "B", "C"] and chunk["state"] == "FAILED" and "救済" in chunk["error"], chunk
    assert data["counts"]["failed_chunks"] == 1, data
elif case.name == "y2":
    write("notes.txt", "an original line\n")
    status, data, out = search("markdown", [("A", "source: notes.txt:1")])
    assert status == 0, data
    report = (out / "result.md").read_text(encoding="utf-8")
    assert not any(line.startswith("## 偽の見出し") for line in report.splitlines()), report
    assert "fixture-end" not in report, report
    for key in ("what", "why", "mishearing", "summary", "says", "passage-mishearing", "unknown-id"):
        normalized = f"fixture-{key} ## 偽の見出し {key} " + "長" * 210
        assert normalized[:199] + "…" in report, (key, report)
    record, = data["records"]
    for key in ("what", "why", "mishearing"):
        raw = f"fixture-{key} \t \n## 偽の見出し {key}\r\n " + "長" * 210 + "fixture-end"
        assert record[key] == raw, record
elif case.name == "y4":
    write("yes.txt", "related source line\n")
    write("no.txt", "unrelated source line\n")
    status, data, out = search("snippet-keys", [("A", "source: yes.txt:1"), ("B", "source: no.txt:1")])
    assert status == 0 and data["status"] == "COMPLETE" and data["counts"]["failed_chunks"] == 0, data
    excerpts = {excerpt["record_id"]: excerpt["quotes"] for excerpt in data["excerpts"]}
    assert excerpts == {"A": [{"line": 1, "text": "related source line"}], "B": []}, excerpts
    report = (out / "result.md").read_text(encoding="utf-8")
    assert "summary for yes.txt" in report and "summary for no.txt" not in report, report
    assert "読みに失敗" not in report and "unrelated source line" not in report, report
    for name in ("result.json", "result.md", "hits.json"):
        assert "fixture-unknown-key-value" not in (out / name).read_text(encoding="utf-8"), name
elif case.name == "z11d":
    status, data, out = search("markdown-comment", [("A", "note: markdown comment")], "--skip-verbatim")
    assert status == 0 and data["records"][0]["what"] == "review <!-- hidden -->", data
    report = (out / "result.md").read_text(encoding="utf-8")
    assert "review &lt;!-- hidden -->" in report and "<!--" not in report, report
elif case.name == "y6af":
    topic = "fixture topic {{TOPIC}} {{BODY}}"
    body = "note: fixture record {{TOPIC}} {{BODY}} </records> after marker"
    status, data, out = search("prompt-literals", [("A", body)], "--topic", topic, "--skip-verbatim")
    assert status == 0 and data["topic"] == topic, data
    prompt = (out / "calls/scan_p1-ledger-1.prompt.txt").read_text(encoding="utf-8")
    assert f"\n{topic}\n" in prompt, prompt
    assert prompt.count("</records>") == 1, prompt
    enclosed = prompt.split("<records>\n", 1)[1].split("\n</records>", 1)[0]
    assert body.replace("</records>", "&lt;/records&gt;") in enclosed, enclosed
elif case.name == "y6b":
    for name in ("type.txt", "range.txt"):
        write(name, "".join(f"{name} original line {n}\n" for n in range(1, 7)))
    status, data, out = search("line-types", [("A", "source: type.txt:2"), ("B", "source: range.txt:4")], "--pad", "1")
    assert status == 0 and data["status"] == "COMPLETE", data
    assert data["counts"]["invalid_passages_dropped"] == 4, data
    excerpts = {excerpt["record_id"]: excerpt for excerpt in data["excerpts"]}
    assert [(excerpts[hid]["line_from"], excerpts[hid]["line_to"]) for hid in ("A", "B")] == [(1, 3), (3, 5)], excerpts
    assert excerpts["A"]["quotes"] == [{"line": 3, "text": "type.txt original line 3"}], excerpts
    assert excerpts["B"]["quotes"] == [{"line": 3, "text": "range.txt original line 3"}], excerpts
elif case.name == "y6c":
    status, data, out = search("save-call", [("A", "note: request evidence")], "--skip-verbatim")
    assert status == 0, data
    calls = out / "calls"
    request, = calls.glob("*.prompt.txt")
    answer, = calls.glob("*.try0.out.txt")
    assert request.name.removesuffix(".prompt.txt") == answer.name.removesuffix(".try0.out.txt"), (request, answer)
    prompt = request.read_text(encoding="utf-8")
    assert "<records>\n" in prompt and "note: request evidence" in prompt, prompt
    assert json.loads(answer.read_text(encoding="utf-8")) == {"hits": [{"id": "A", "strength": "直接"}]}, answer
elif case.name == "y6e":
    records = [(hid, "note: ID fixture") for hid in ("42", "['fixture']", "True", "CamelCase", "DUP", "DUP")]
    status, data, out = search("id-types", records, "--skip-verbatim", "--chunk-tokens", "1000")
    assert status == 0, data
    assert {(record["id"], record["line"]) for record in data["records"]} == {("DUP@10", 10), ("DUP@12", 12)}, data
    chunk, = data["chunks"]
    assert set(chunk["ids"]) == {"42", "['fixture']", "True", "CamelCase", "DUP@10", "DUP@12"}, chunk
else:
    raise AssertionError(f"unexpected case: {case}")
Q_AGENTPATH_EXERCISE

q_run_agentpath() {
  q_env python3 -B "$Q_AGENTPATH_DIR/exercise.py" "$Q_SEARCH" "$Q_SKILL" "$Q_AGENTPATH_DIR" "$1"
}
assert_ok "X4: merged windows clip quotes per record and distinguish failed and empty reads" q_run_agentpath x4
assert_ok "X7: truncated hits retry and survive exhaustion with a FAILED chunk" q_run_agentpath x7
assert_ok "X11: missing, invalid, duplicated, and unexpected snippet answers retry" q_run_agentpath x11
assert_ok "X12: grep judge failure remains unjudged while completed chunks count their decisions" q_run_agentpath x12
assert_ok "X13: prompt boundaries and attributes are escaped while original quotes are preserved" q_run_agentpath x13
assert_ok "X16: a custom agent is timed out and retried at the requested limit" q_run_agentpath x16
assert_ok "Y1: a truncated third hit preserves both preceding hits and marks the chunk FAILED" q_run_agentpath y1
assert_ok "Y2: model text in Markdown stays on one line and fits 200 characters while record JSON stays raw" q_run_agentpath y2
assert_ok "Y4: boolean relevance controls quotes and extra model keys cannot turn successful reads into failures" q_run_agentpath y4
assert_ok "Z11d: Markdown comment openers in model free text are escaped while the JSON stays raw" q_run_agentpath z11d
assert_ok "Y6a/Y6f: literal template markers and an embedded closing tag remain inside the prompt material" q_run_agentpath y6af
assert_ok "Y6b: quoted lines reject booleans, strings and numbers outside the snippet but within the source" q_run_agentpath y6b
assert_ok "Y6c: calls contains the request text and raw answer for the same attempt" q_run_agentpath y6c
assert_ok "Y6e: wrong-type and wrong-case IDs are dropped while duplicate IDs identify different lines" q_run_agentpath y6e

# X15/X17. Planning settings are literal input, and each output directory
# can serve only one active run and retain at most one completed result.
q_check_planning_defaults() {
  q_env python3 - "$Q_SEARCH" "$Q_ROOT" <<'PY'
import json
import os
from pathlib import Path
import subprocess
import sys

script, test_root = sys.argv[1:]
case = Path(test_root) / "planning-defaults"
case.mkdir()
kit = case / "kit"
kit.mkdir()
ledger = case / "ledger.yaml"
ledger.write_text("facts:\n  - id: F-PLAN\n    title: Planning input\n", encoding="utf-8")
marker = case / "config-executed"
(kit / "config.env").write_text(
    f'echo unsafe > "{marker}"\nMSEARCH_PASSES=1\nMSEARCH_PARALLEL="4" # comment\n'
    "MSEARCH_CHUNK_TOKENS=140\n",
    encoding="utf-8",
)
base = dict(os.environ, MSEARCH_KIT_ROOT=str(kit))
keys = ("passes", "parallel", "chunk_tokens")

def plan(label, expected, env, *flags):
    out = case / label
    run = subprocess.run(
        [sys.executable, script, "--topic", label, "--ledger", str(ledger),
         "--dry-run", "--out", str(out), *flags],
        env=env, capture_output=True, text=True,
    )
    assert run.returncode == 0, run.stderr
    data = json.loads((out / "plan.json").read_text(encoding="utf-8"))
    assert data["passes"] == expected[0], (label, data["passes"])
    assert {chunk["pass"] for chunk in data["chunks"]} == set(range(1, expected[0] + 1)), data
    assert tuple(data[key] for key in keys) == expected, (label, data)
    assert not marker.exists(), "config.env was executed"

plan("config", (1, 4, 140), base)
env = dict(base, MSEARCH_PASSES="2", MSEARCH_PARALLEL="5", MSEARCH_CHUNK_TOKENS="160")
plan("environment", (2, 5, 160), env)
plan("arguments", (3, 6, 180), env, "--passes", "3", "--parallel", "6", "--chunk-tokens", "180")
PY
}
assert_ok "X15: planning flags beat environment, literal config, and defaults without executing config" q_check_planning_defaults

q_check_output_claim() {
  q_env python3 - "$Q_SEARCH" "$Q_ROOT" <<'PY'
import json
from pathlib import Path
import runpy
import subprocess
import sys

script, test_root = sys.argv[1:]
case = Path(test_root) / "output-claim"
case.mkdir()
ledger = case / "ledger.yaml"
ledger.write_text("facts:\n  - id: F-OUT\n    title: Output isolation\n", encoding="utf-8")

def run(topic, out, *flags):
    return subprocess.run(
        [sys.executable, script, "--topic", topic, "--ledger", str(ledger),
         "--passes", "1", "--skip-verbatim", "--out", str(out), *flags],
        capture_output=True, text=True,
    )

def files(out):
    return {p.relative_to(out): p.read_bytes() for p in out.rglob("*") if p.is_file()}

out = case / "first-run"
out.mkdir()
first = run("first", out)
assert first.returncode == 0, first.stderr
assert json.loads((out / "result.json").read_text(encoding="utf-8"))["status"] == "COMPLETE"
before = files(out)
for flags in ((), ("--dry-run",)):
    second = run("second", out, *flags)
    assert second.returncode == 2, second
    assert files(out) == before

for name in ("result.json", "plan.json", "hits.json", "calls"):
    out = case / name.removesuffix(".json")
    out.mkdir()
    artifact = out / name
    if name == "calls":
        artifact.mkdir()
    else:
        artifact.write_text("old artifact\n", encoding="utf-8")
    refusal = run(name, out, "--dry-run")
    assert refusal.returncode == 2, refusal
    assert list(out.iterdir()) == [artifact]

out = case / "race"
out.mkdir()
claim_output = runpy.run_path(script)["claim_output"]
with claim_output(out, reuse_dry=True) as log:
    log.write("first run\n")
    log.flush()
    (out / "plan.json").write_text(json.dumps({
        "topic": "active", "dry_run": True, "chunks": [], "planned_calls": 0,
    }), encoding="utf-8")
    before = files(out)
    contender = run("contender", out, "--dry-run")
    assert contender.returncode == 2 and "使用中" in contender.stderr, contender
    assert files(out) == before
after_release = run("after release", out, "--dry-run")
assert after_release.returncode == 0, after_release.stderr
assert json.loads((out / "plan.json").read_text(encoding="utf-8"))["topic"] == "after release"
PY
}
assert_ok "X17: prior artifacts are preserved and concurrent runs cannot share an output directory" q_check_output_claim


# Z1/Z3. Parser coverage identifies unscanned lines without exposing their
# contents, and record/citation locations follow LF-delimited line numbers.
q_check_round5_parser() {
  q_env python3 -B - "$Q_SEARCH" "$Q_ROOT" "$1" <<'PY'
import json
from pathlib import Path
import shlex
import subprocess
import sys

script, root, check = sys.argv[1:]
case = Path(root) / f"parser-{check}"
case.mkdir()
agent = case / "agent.py"
agent.write_text('''import json
import re
import sys

prompt = sys.stdin.read()
if "<records>\\n" in prompt:
    hits = [{"id": "F-PHYSICAL", "strength": "直接"}] if "- id: F-PHYSICAL" in prompt else []
    print(json.dumps({"hits": hits}))
else:
    print(json.dumps({"snippets": [
        {"snippet": sid, "relevant": True, "passages": [{"lines": [4, 4]}]}
        for sid in re.findall(r'<snippet id="([^"]+)"', prompt)
    ]}))
''', encoding="utf-8")

def run(label, *flags):
    out = case / "results" / label
    proc = subprocess.run(
        [sys.executable, "-B", script, "--topic", "fixture", "--out", str(out),
         "--agent", shlex.join([sys.executable, str(agent)]), "--retries", "0", "--passes", "1", *flags],
        capture_output=True, text=True,
    )
    return proc, out

def write(name, body):
    path = case / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return str(path)

def read_json(out, name):
    return json.loads((out / name).read_text(encoding="utf-8"))

if check == "coverage":
    ledger = write("ledgers/ledger.yaml", """meta:
  format: v1

facts:
  - id: F-GOOD
    note: searchable fixture
  - title: MIXED-Z1
    note: MIXED-Z1
holes:
  - title: UNREAD-Z1
    note: UNREAD-Z1

  - title: UNREAD-Z1

  - title: UNREAD-Z1

  - title: UNREAD-Z1

  - title: UNREAD-Z1

  - title: UNREAD-Z1

  - title: UNREAD-Z1
""")
    journal = write("journal.md", """# Fixture journal

## D-OLD
UNREAD-JOURNAL-Z1

### D-2026-01-01-01 Real entry
First judgment.
<!--
### D-YYYY-MM-DD-NN COMMENT-Z1
source: COMMENT-Z1
-->
### D-2026-01-01-02 Real entry <!-- COMMENT-Z1 -->
Second judgment.
<!-- COMMENT-Z1 -->
""")
    expected = [
        {"file": ledger, "records": 1, "preface_lines": 4, "unread_lines": 10,
         "unread_ranges": [[7, 8], [10, 11], [13, 13], [15, 15], [17, 17]]},
        {"file": journal, "records": 2, "preface_lines": 1, "unread_lines": 7,
         "unread_ranges": [[3, 4], [8, 11], [14, 14]]},
    ]
    flags = ("--ledger", ledger, "--journal", journal)
    summaries = (
        "読まない前書き 4 行・記録に入らなかった行 10 行（L7〜L8、L10〜L11、L13、L15、L17、…）",
        "読まない前書き 1 行・記録に入らなかった行 7 行（L3〜L4、L8〜L11、L14）",
    )
    dry, dry_out = run("dry", *flags, "--dry-run")
    assert dry.returncode == 0, dry.stderr
    plan = read_json(dry_out, "plan.json")
    assert plan["parse_coverage"] == expected, plan
    assert [hid for row in plan["chunks"] for hid in row["ids"]] == ["F-GOOD", "D-2026-01-01-01", "D-2026-01-01-02"], plan
    assert all(summary in dry.stdout for summary in summaries), dry.stdout
    proc, out = run("read", *flags)
    assert proc.returncode == 0, proc.stderr
    counts = read_json(out, "result.json")["counts"]
    assert counts["parse_coverage"] == expected and counts["preface_lines"] == 5 and counts["unread_lines"] == 17, counts
    assert read_json(out, "plan.json")["parse_coverage"] == expected
    report = (out / "result.md").read_text(encoding="utf-8").split("## A.", 1)[0]
    assert all(summary in report for summary in summaries), report
    prompts = "\n".join(p.read_text(encoding="utf-8") for p in (out / "calls").glob("*.prompt.txt"))
    assert all(marker in prompts for marker in ("searchable fixture", "First judgment.", "Second judgment.")), prompts
    for marker in ("UNREAD-Z1", "MIXED-Z1", "UNREAD-JOURNAL-Z1", "D-OLD", "COMMENT-Z1", "D-YYYY-MM-DD-NN"):
        assert marker not in prompts + report + dry.stdout, marker

elif check == "zero":
    good = write("ledgers/good.yaml", "facts:\n  - id: F-GOOD\n")
    empty = write("ledgers/unrecognized.yaml", "  - id: F-NO-SECTION\n")
    journal = write("unrecognized.md", "<!--\n### D-YYYY-MM-DD-NN Example\n-->\n")
    for label, flags, name, pattern in (
        ("ledger", ("--ledger", empty), empty, r"^[ \t]*-[ \t]+id:[ \t]*(\S+)"),
        ("journal", ("--journal", journal), journal, r"^###\s+(D-[0-9A-Za-z-]+)"),
    ):
        proc, out = run(label, "--ledger", good, *flags, "--dry-run")
        assert proc.returncode == 2 and name in proc.stderr and pattern in proc.stderr, proc
        assert not (out / "plan.json").exists(), out
    meeting = write("meeting.txt", "Fixture transcript\n")
    proc, out = run("skip", "--ledger", empty, "--journal", journal, "--skip-ledger", "--meeting", meeting, "--dry-run")
    assert proc.returncode == 0, proc.stderr
    plan = read_json(out, "plan.json")
    assert plan["parse_coverage"] == [] and plan["files"] == [] and plan["explicit_meetings"] == [meeting], plan

elif check == "project":
    good = write("ledgers/good.yaml", "facts:\n  - id: F-GOOD\n")
    proc, out = run("missing", "--project", "fixture-missing-project", "--ledger", good, "--dry-run")
    assert proc.returncode == 2 and "--project" in proc.stderr and "projects/fixture-missing-project" in proc.stderr, proc
    assert not (out / "plan.json").exists(), out

elif check == "physical":
    ledger = write("ledgers/ledger.yaml", "facts:\n  - id: F-SEPARATORS\n"
                   "    note: before\f  - id: F-FAKE\u2028more\n"
                   "  - id: F-PHYSICAL\n    source: notes.txt:4\n")
    source = case / "notes.txt"
    source.write_bytes("first\r\npage\fcontinues\nsegment\u2028continues\nphysical target\r interior\r\n".encode("utf-8"))
    proc, out = run("read", "--ledger", ledger, "--pad", "0")
    assert proc.returncode == 0, proc.stderr
    result = read_json(out, "result.json")
    record, = result["records"]
    n, text = subprocess.check_output(["grep", "-nF", "physical target", str(source)]).removesuffix(b"\n").split(b":", 1)
    assert record["id"] == "F-PHYSICAL" and record["line"] == int(n) == 4, record
    excerpt, = result["excerpts"]
    assert excerpt["quotes"] == [{"line": int(n), "text": text.removesuffix(b"\r").decode("utf-8")}], excerpt
    plan = read_json(out, "plan.json")
    assert [hid for row in plan["chunks"] for hid in row["ids"]] == ["F-SEPARATORS", "F-PHYSICAL"], plan
else:
    raise AssertionError(check)
PY
}
assert_ok "Z1: coverage counts unread lines and preface separately, and journal comments never reach prompts" q_check_round5_parser coverage
assert_ok "Z1: each zero-record input exits 2 unless ledger reading is skipped" q_check_round5_parser zero
assert_ok "Z1: a missing project directory exits 2 despite a valid ledger" q_check_round5_parser project
assert_ok "Z3: FF and U+2028 preserve grep line numbers, and CRLF preserves interior CR in quotes" q_check_round5_parser physical

q_check_round5_sources() {
  q_env python3 -B - "$Q_SEARCH" "$Q_ROOT" "$1" <<'PY'
import json
import os
from pathlib import Path
import subprocess
import sys

script, test_root, check = sys.argv[1:]
case = Path(test_root) / f"round5-sources-{check}"
kit = case / "kit"
project = kit / "projects" / "fixture"
ledger = project / "ledgers" / "ledger.yaml"
transcripts = project / "transcripts"
trace = case / "trace"
for directory in (ledger.parent, transcripts, trace):
    directory.mkdir(parents=True)
rules = case / "rules.json"
env = dict(os.environ, MSEARCH_KIT_ROOT=str(kit), Q_RULES=str(rules), Q_TRACE=str(trace))

def write_records(records):
    ledger.write_text("facts:\n" + "".join(
        f"  - id: {record}\n    source: {source}\n" for record, source in records.items()
    ), encoding="utf-8")
    rules.write_text(json.dumps({"hits": list(records)}), encoding="utf-8")

def run(name, *flags):
    out = case / name
    completed = subprocess.run([sys.executable, script, "--topic", name, "--out", str(out),
                                "--agent", env["AGENT_CMD"], "--passes", "1", "--pad", "0", "--retries", "0", *flags],
                               env=env, capture_output=True, text=True, check=False)
    return completed, out

def result(name, *flags):
    completed, out = run(name, *flags)
    assert completed.returncode == 0, completed.stderr
    data = json.loads((out / "result.json").read_text(encoding="utf-8"))
    report = (out / "result.md").read_text(encoding="utf-8")
    return data, report

if check == "z4":
    invalid = transcripts / "unreadable.txt"
    invalid.write_bytes("合図".encode("cp932"))
    good = transcripts / "readable.txt"
    good.write_text("readable transcript\n", encoding="utf-8")
    mail = project / "mail"
    mail.mkdir()
    invalid_mail = mail / "2026-01-13.txt"
    invalid_mail.write_bytes(invalid.read_bytes())
    write_records({"A": "transcripts/unreadable.txt:1", "B": "unreadable L1、readable L1",
                   "C": "mail:2026-01-13"})
    data, report = result("references", "--project", "fixture", "--mail-dir", str(mail))
    issues = {source["id"]: source["why"] for source in data["unresolved_sources"]}
    assert set(issues) == {"A", "B", "C"}, data
    assert all(f.name in issues[key] and "文字コード" in issues[key]
               for key, f in (("A", invalid), ("B", invalid), ("C", invalid_mail))), issues
    assert [(item["record_id"], item["file"]) for item in data["excerpts"]] == [("B", str(good))], data
    assert "文字コード" in report and invalid.name in report, report
    data, report = result("meetings", "--skip-ledger", "--meeting", str(invalid), "--meeting", str(good))
    issue, = data["unresolved_sources"]
    assert issue["id"] is None and issue["file"] == str(invalid) and "文字コード" in issue["why"], data
    assert [item["file"] for item in data["excerpts"]] == [str(good)], data
    assert "--meeting" in report and invalid.name in report, report
    for flag in ("ledger", "journal"):
        bad = case / f"invalid-{flag}.txt"
        bad.write_bytes(invalid.read_bytes())
        flags = ["--ledger", str(ledger)] if flag == "journal" else []
        completed, out = run(flag, *flags, f"--{flag}", str(bad))
        assert completed.returncode == 2 and str(bad) in completed.stderr, completed
elif check == "z6":
    source = project / "notes.txt"
    source.write_text("first\nsecond\nthird\n", encoding="utf-8")
    write_records({"A": "notes.txt:1", "B": "notes.txt:3"})
    data, report = result("windows", "--project", "fixture", "--max-windows", "1")
    assert data["counts"]["skipped_windows"] == 1, data
    assert [item["record_id"] for item in data["excerpts"]] == ["A"], data
    scope = report.split("## A. 台帳・判断台帳で拾った記録", 1)[0]
    assert "上限（--max-windows）で読まなかった窓 1 件" in scope, scope
elif check == "z7":
    outside = kit / "local" / "secrets" / "x.env"
    note = project / "notes.txt"
    note.write_text("inside the project\n", encoding="utf-8")
    root_note = kit / "root-notes.txt"
    root_note.write_text("inside the synthetic kit\n", encoding="utf-8")
    write_records({"A": f"{outside}:1", "B": "notes.txt:1", "C": "root-notes.txt:1"})
    for name, flags in (("project", ("--project", "fixture")), ("ledger", ("--ledger", str(ledger)))):
        data, _ = result(name, *flags)
        issues = {source["id"]: source["why"] for source in data["unresolved_sources"]}
        assert "根の外" in issues["A"] and str(outside) in issues["A"] and "C" in issues, data
        assert [(item["record_id"], item["file"]) for item in data["excerpts"]] == [("B", str(note))], data
    write_records({"C": "root-notes.txt:1"})
    data, _ = result("explicit-root", "--project", "fixture", "--source-root", str(kit))
    assert [item["file"] for item in data["excerpts"]] == [str(root_note)], data
elif check == "z8":
    transcript = transcripts / "clock.txt"
    transcript.write_text("[00:00:10] last time\n", encoding="utf-8")
    write_records({"A": "talk:clock@00:01:11", "B": "talk:clock@00:01:10",
                   "C": "clock.txt 00:00:10〜00:01:11"})
    data, _ = result("clock", "--project", "fixture")
    issues = {source["id"]: source["why"] for source in data["unresolved_sources"]}
    assert set(issues) == {"A", "C"}, data
    assert all("時刻が逐語の範囲の外" in issue and "00:01:11" in issue for issue in issues.values()), issues
    assert [(item["record_id"], item["quotes"][0]["line"]) for item in data["excerpts"]] == [("B", 1)], data
elif check == "z11a":
    names = ("clock.txt", "notes.md", "captions.srt", "captions-upper.VTT")
    for name in (*names, "clock.m4a", "audio-only.m4a"):
        (transcripts / name).write_text("[00:00:10] transcript fixture\n", encoding="utf-8")
    write_records({f"F-{i}": f"talk:{Path(name).stem}@00:00:10"
                   for i, name in enumerate((*names, "audio-only.m4a"))})
    data, _ = result("extensions", "--project", "fixture")
    assert {Path(item["file"]).name for item in data["excerpts"]} == set(names), data
    issue, = data["unresolved_sources"]
    assert issue["id"] == "F-4", data
else:
    raise AssertionError(f"unexpected case: {check}")
PY
}
assert_ok "Z4: source encoding errors identify the file and preserve readable references and explicit meetings" q_check_round5_sources z4
assert_ok "Z6: the count and coverage show windows dropped at the configured limit" q_check_round5_sources z6
assert_ok "Z7: project and direct ledger defaults stay within their source roots" q_check_round5_sources z7
assert_ok "Z8: timestamps over 60 seconds beyond the last entry are unresolved" q_check_round5_sources z8
assert_ok "Z11a: transcript matching considers only the supported text extensions" q_check_round5_sources z11a

# Z5/Z7. Reusing a dry plan and placing its successor both go through the CLI.
q_check_round5_output() {
  q_env python3 - "$Q_SEARCH" "$Q_ROOT" "$1" <<'PY'
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

script, test_root, check = sys.argv[1:]
case = Path(test_root) / f"round5-output-{check}"
kit = case / "kit"
kit.mkdir(parents=True)
ledger = case / "ledger.yaml"
ledger.write_text("facts:\n  - id: F-OUT\n    title: Output isolation\n", encoding="utf-8")
base = dict(os.environ, MSEARCH_KIT_ROOT=str(kit))

def run(*flags, env=base, topic="fixture"):
    return subprocess.run([sys.executable, script, "--topic", topic, "--ledger", str(ledger),
                           "--passes", "1", "--skip-verbatim", *map(str, flags)],
                          env=env, capture_output=True, text=True)

def read_plan(out):
    return json.loads((out / "plan.json").read_text(encoding="utf-8"))

if check == "parent":
    parent = case / "reports"
    env = dict(base, MSEARCH_OUT_DIR=str(parent))
    runs = [run("--dry-run", env=env) for _ in range(2)]
    assert all(run.returncode == 0 for run in runs), runs
    children = set(parent.iterdir())
    assert len(children) == 2 and all(p.is_dir() for p in children), children
    for child in children:
        assert re.fullmatch(r"meaning-search-\d{8}-\d{6}-fixture-.+", child.name), child
        assert read_plan(child)["dry_run"] is True and (child / "run.log").is_file(), child
    assert {Path(run.stdout.splitlines()[-1]).parent for run in runs} == children
    explicit = case / "explicit"
    assert run("--dry-run", "--out", explicit, env=env).returncode == 0
    assert (explicit / "plan.json").is_file() and set(parent.iterdir()) == children
elif check == "reuse":
    out = case / "explicit"
    first = run("--dry-run", "--out", out, topic="first")
    assert first.returncode == 0, first
    with (out / "run.log").open("a", encoding="utf-8") as log:
        log.write("prior dry run sentinel\n")
    second = run("--dry-run", "--out", out, topic="second")
    assert second.returncode == 0 and read_plan(out)["topic"] == "second", second
    assert "prior dry run sentinel" not in (out / "run.log").read_text(encoding="utf-8")

    legacy = case / "legacy"
    shutil.copytree(out, legacy)
    legacy_plan = read_plan(legacy)
    del legacy_plan["dry_run"]
    (legacy / "plan.json").write_text(json.dumps(legacy_plan), encoding="utf-8")
    for saved in (out, legacy):
        final = run("--out", saved, "--agent", base["AGENT_CMD"], topic="real")
        assert final.returncode == 0, final
        plan = read_plan(saved)
        assert plan["topic"] == "real" and plan["dry_run"] is False, plan
        result = json.loads((saved / "result.json").read_text(encoding="utf-8"))
        assert result["status"] == "COMPLETE" and result["topic"] == "real", result
elif check == "ineligible":
    out = case / "failed-real"
    failed = run("--out", out, "--agent", case / "missing-agent")
    assert failed.returncode == 2 and "--agent" in failed.stderr, failed
    assert {p.name for p in out.iterdir()} == {"plan.json", "run.log"}, out
    before = {p.name: p.read_bytes() for p in out.iterdir()}
    retry = run("--dry-run", "--out", out)
    assert retry.returncode == 2 and {p.name: p.read_bytes() for p in out.iterdir()} == before, retry

    dry = case / "dry"
    assert run("--dry-run", "--out", dry).returncode == 0
    extra = dry / "extra.txt"
    extra.write_text("unrelated fixture", encoding="utf-8")
    assert run("--dry-run", "--out", dry).returncode == 2
    assert extra.read_text(encoding="utf-8") == "unrelated fixture"

    linked = case / "linked"
    linked.mkdir()
    shutil.copyfile(dry / "plan.json", linked / "plan.json")
    (linked / "run.log").symlink_to(dry / "run.log")
    log = (dry / "run.log").read_bytes()
    assert run("--dry-run", "--out", linked).returncode == 2
    assert (linked / "run.log").is_symlink() and (dry / "run.log").read_bytes() == log
elif check == "kit-paths":
    docs = kit / "docs"
    local = kit / "local"
    docs.mkdir()
    local.mkdir()
    (local / "into-docs").symlink_to(docs, target_is_directory=True)
    (docs / "into-local").symlink_to(local, target_is_directory=True)

    for dest in (kit, docs / "report", local / "into-docs" / "report"):
        refused = run("--dry-run", "--out", dest)
        assert refused.returncode == 2 and "local/ または projects/" in refused.stderr, refused
    for env in (dict(base, MSEARCH_OUT_DIR=str(docs / "env")), dict(base, TMPDIR=str(docs))):
        refused = run("--dry-run", env=env)
        assert refused.returncode == 2 and "local/ または projects/" in refused.stderr, refused
    assert list(docs.iterdir()) == [docs / "into-local"], list(docs.iterdir())
    assert not (kit / "plan.json").exists()

    for dest in (local / "report", kit / "projects" / "fixture" / "report",
                 case / "outside", docs / "into-local" / "via-symlink"):
        allowed = run("--dry-run", "--out", dest)
        assert allowed.returncode == 0 and read_plan(dest)["dry_run"] is True, allowed
PY
}
assert_ok "Z5: MSEARCH_OUT_DIR creates a unique timestamped child per run and yields to --out" q_check_round5_output parent
assert_ok "Z5: explicit dry-run outputs can be replaced by another dry run or a completed run" q_check_round5_output reuse
assert_ok "Z5: failed real runs, unexpected files, and linked logs are preserved" q_check_round5_output ineligible
assert_ok "Z7: output within the kit stays in local or projects after resolving symlinks" q_check_round5_output kit-paths

assert_absent "Q3/Q9: neither PATH decoy was ever invoked" "$Q_TRAP_LOG"
