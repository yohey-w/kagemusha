#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# E. cron wiring — morning_brief.sh end to end, with a fake AI CLI.
#
# What breaks in production is never the prompt; it is the wiring: cron's PATH
# doesn't find the CLI, the log lands nowhere, a failed run still exits 0 and
# the scheduler reports success forever. This group asserts the wiring and
# nothing about model output.
#
# NO AI CLI IS CALLED. The shim lives in a throwaway $HOME/.local/bin and the
# run gets a deliberately cron-like PATH (/usr/bin:/bin) — so the shim is
# reachable ONLY because of the PATH line at the top of morning_brief.sh. That
# line is the fix for the most common cron failure in this kit, and this is
# what proves it still works. Using a fake HOME also guarantees a real `claude`
# on the developer's machine can never be the thing that runs.
#
# NOTHING LEAVES THE MACHINE. The ntfy push is pointed at a one-shot HTTP sink
# on 127.0.0.1, so the notification path is exercised for real (URL, headers,
# body) while the only host contactable is loopback.
# ═══════════════════════════════════════════════════════════════════════════
# shellcheck shell=bash
# shellcheck disable=SC2154  # globals come from scripts/test.sh

group "E. cron wiring (morning_brief.sh, fake CLI, loopback ntfy)"

E_KIT="$TEST_TMP/e_kit";  kit_copy "$E_KIT"
E_HOME="$TEST_TMP/e_home"
E_BIN="$E_HOME/.local/bin"
E_LOOP="$TEST_TMP/e_loop"
mkdir -p "$E_BIN" "$E_LOOP"

# ── the fake agent CLI: records argv, writes the notify file the prompt names ─
cat > "$E_BIN/claude" <<'SHIM'
#!/usr/bin/env bash
: > "$SHIM_ARGS"
for a in "$@"; do printf '%s\n' "$a" >> "$SHIM_ARGS"; done
printf 'fake-cli: %d args\n' "$#"
if [[ "${SHIM_WRITE_NOTIFY:-1}" == "1" ]]; then
  # the notify path is carried inside the prompt; finding it there is itself an
  # assertion that the prompt still tells the agent where to write its summary
  for a in "$@"; do
    p="$(printf '%s' "$a" | grep -oE '[^[:space:]]+\.notify\.txt' | head -n 1)"
    if [[ -n "$p" ]]; then printf 'SUMMARY 3 waiting on you / next deadline in 2 days\n' > "$p"; break; fi
  done
fi
exit "${SHIM_EXIT:-0}"
SHIM
chmod +x "$E_BIN/claude"

# ── one-shot loopback ntfy sink ────────────────────────────────────────────
E_SINK_LOG="$TEST_TMP/e_sink.log"
E_SINK_PORT_FILE="$TEST_TMP/e_sink.port"
cat > "$TEST_TMP/e_sink.py" <<'PY'
import http.server, sys
log_path, port_path = sys.argv[1], sys.argv[2]
class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        with open(log_path, "a") as f:
            f.write("POST %s\n" % self.path)
            for k, v in self.headers.items():
                f.write("HEADER %s: %s\n" % (k, v))
            f.write("BODY %s\n" % body.decode("utf-8", "replace").replace("\n", " "))
        self.send_response(200); self.send_header("Content-Length", "0"); self.end_headers()
    def log_message(self, *a): pass
srv = http.server.HTTPServer(("127.0.0.1", 0), H)
with open(port_path, "w") as f:
    f.write(str(srv.server_address[1]))
srv.handle_request()   # exactly one request, then exit
PY
timeout 60 python3 "$TEST_TMP/e_sink.py" "$E_SINK_LOG" "$E_SINK_PORT_FILE" >/dev/null 2>&1 &
for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
  [[ -s "$E_SINK_PORT_FILE" ]] && break
  sleep 0.2
done
E_PORT="$(cat "$E_SINK_PORT_FILE" 2>/dev/null || true)"
assert_nonempty_str "E0: loopback ntfy sink is listening" "$E_PORT"

E_CFG="$TEST_TMP/e_config.env"
write_e_cfg() {  # write_e_cfg <ntfy_enabled> <topic> <server>
  cat > "$E_CFG" <<CFG
PROJECT_ROOT="$E_LOOP"
SSOT_DIR="\$PROJECT_ROOT/ssot"
BRIEF_DIR="\$PROJECT_ROOT/briefs"
LOG_DIR="\$PROJECT_ROOT/logs"
QUEUE_FILE="\$PROJECT_ROOT/approval_queue.md"
AGENT_CMD="claude"
AGENT_MODEL=""
AGENT_FLAGS=""
AGENT_TIMEOUT=60
NTFY_ENABLED=$1
NTFY_TOPIC="$2"
NTFY_SERVER="$3"
CFG
}

E_SHIM_EXIT=0
E_SHIM_NOTIFY=1
# run_brief — invoke the shipped script the way cron does: bare path, a minimal
# environment, and a PATH that does NOT contain the CLI's directory.
#
# The proxy variables are a hard floor under "nothing leaves the machine": any
# non-loopback request is routed to a dead port on 127.0.0.1 and dies there, so
# the guarantee does not depend on morning_brief.sh honouring NTFY_SERVER. (It
# does honour it — E3 asserts that — but a test whose safety rests on the code
# it is testing is not a safety property.)
run_brief() {
  env -i HOME="$E_HOME" PATH="/usr/bin:/bin" LOOP_CONFIG="$E_CFG" \
      http_proxy="http://127.0.0.1:1"  https_proxy="http://127.0.0.1:1" \
      HTTP_PROXY="http://127.0.0.1:1"  HTTPS_PROXY="http://127.0.0.1:1" \
      ALL_PROXY="http://127.0.0.1:1" \
      no_proxy="127.0.0.1,localhost"   NO_PROXY="127.0.0.1,localhost" \
      SHIM_ARGS="$E_ARGS" SHIM_EXIT="$E_SHIM_EXIT" SHIM_WRITE_NOTIFY="$E_SHIM_NOTIFY" \
      "$E_KIT/scripts/morning_brief.sh"
}
e_notify_files() { find "$E_LOOP/briefs" -name '*.notify.txt' -type f 2>/dev/null; }

# ── case 1: happy path, notifications off ──────────────────────────────────
E_ARGS="$TEST_TMP/e_args1.txt"
write_e_cfg 0 "unused" "http://127.0.0.1:${E_PORT}"
run_brief > "$TEST_TMP/e_run1.out" 2>&1; e_rc1=$?
assert_eq "E1: exits 0 when the CLI succeeds" "0" "$e_rc1"
assert_file "E1: the CLI shim ran — PATH reached \$HOME/.local/bin" "$E_ARGS"
assert_eq "E1: the CLI was invoked as: <cmd> -p <prompt>" "-p" "$(head -n 1 "$E_ARGS" 2>/dev/null)"
assert_grep "E1: the prompt names the board output path" "$E_LOOP/briefs/" "$E_ARGS"
assert_grep "E1: the prompt still forbids outward operations" "STRICTLY FORBIDDEN" "$E_ARGS"
assert_grep "E1: the prompt still names the approval queue" "$E_LOOP/approval_queue.md" "$E_ARGS"

e_log1="$(find "$E_LOOP/logs" -name 'morning_brief_2*.log' -type f 2>/dev/null | head -n 1)"
assert_nonempty_str "E1: a dated agent log file was written" "$e_log1"
assert_grep "E1: agent stdout landed in that log" "fake-cli:" "${e_log1:-/nonexistent}"
assert_grep "E1: the cron log records the run and its exit code" "morning_brief exit=0" \
  "$E_LOOP/logs/morning_brief_cron.log"
assert_nonempty_str "E1: the one-line notify file was produced" "$(e_notify_files)"
assert_empty_str "E1: NTFY_ENABLED=0 → the sink received nothing" "$(cat "$E_SINK_LOG" 2>/dev/null)"

# ── case 2: the CLI fails — propagate, and do not notify ───────────────────
E_ARGS="$TEST_TMP/e_args2.txt"; E_SHIM_EXIT=7; E_SHIM_NOTIFY=0
write_e_cfg 1 "ci-loopback-topic" "http://127.0.0.1:${E_PORT}"
run_brief > "$TEST_TMP/e_run2.out" 2>&1; e_rc2=$?
E_SHIM_EXIT=0; E_SHIM_NOTIFY=1
assert_eq "E2: a failing CLI makes morning_brief exit with the same code" "7" "$e_rc2"
assert_grep "E2: the cron log records the failure" "morning_brief exit=7" \
  "$E_LOOP/logs/morning_brief_cron.log"
assert_empty_str "E2: the stale notify file from the previous run was cleared" "$(e_notify_files)"
assert_empty_str "E2: no summary → nothing pushed (sink still empty)" "$(cat "$E_SINK_LOG" 2>/dev/null)"

# ── case 3: notification enabled — a real request, to loopback only ────────
E_ARGS="$TEST_TMP/e_args3.txt"
run_brief > "$TEST_TMP/e_run3.out" 2>&1; e_rc3=$?
assert_eq "E3: exits 0" "0" "$e_rc3"
assert_file "E3: the ntfy sink received the push" "$E_SINK_LOG"
assert_grep "E3: …on the configured topic path" "POST /ci-loopback-topic" "$E_SINK_LOG"
assert_grep "E3: …with the Title header" "Title: morning board" "$E_SINK_LOG"
assert_grep "E3: …carrying the agent's one-line summary" "SUMMARY 3 waiting on you" "$E_SINK_LOG"
assert_no_grep "E3: nothing was addressed to the public ntfy.sh host" "ntfy.sh" "$E_SINK_LOG"

# ── case 4: no topic configured — no request at all ────────────────────────
E_ARGS="$TEST_TMP/e_args4.txt"
write_e_cfg 1 "" "http://127.0.0.1:${E_PORT}"
e_sink_before="$(wc -c < "$E_SINK_LOG" 2>/dev/null || echo 0)"
run_brief > "$TEST_TMP/e_run4.out" 2>&1; e_rc4=$?
assert_eq "E4: exits 0" "0" "$e_rc4"
assert_eq "E4: an empty NTFY_TOPIC sends nothing" \
  "$e_sink_before" "$(wc -c < "$E_SINK_LOG" 2>/dev/null || echo 0)"

# ── case 5: missing config is a loud failure, not a silent no-op ───────────
E_ARGS="$TEST_TMP/e_args5.txt"
E_CFG_KEEP="$E_CFG"; E_CFG="$TEST_TMP/no_such_config.env"
run_brief > "$TEST_TMP/e_run5.out" 2>&1; e_rc5=$?
E_CFG="$E_CFG_KEEP"
assert_eq "E5: a missing config.env exits 1" "1" "$e_rc5"
assert_grep "E5: …and names the file it wanted" "config not found" "$TEST_TMP/e_run5.out"
assert_absent "E5: the CLI is never invoked without a config" "$TEST_TMP/e_args5.txt"

# ── case 6: config present but a required key missing → refuse to run ──────
E_ARGS="$TEST_TMP/e_args6.txt"
printf 'PROJECT_ROOT="%s"\n' "$E_LOOP" > "$TEST_TMP/e_partial.env"
E_CFG_KEEP="$E_CFG"; E_CFG="$TEST_TMP/e_partial.env"
run_brief > "$TEST_TMP/e_run6.out" 2>&1; e_rc6=$?
E_CFG="$E_CFG_KEEP"
assert_ne "E6: an incomplete config does not exit 0" "0" "$e_rc6"
assert_grep "E6: …and says which key is missing" "SSOT_DIR" "$TEST_TMP/e_run6.out"
assert_absent "E6: the CLI is never invoked with an incomplete config" "$TEST_TMP/e_args6.txt"

# ── the standing guarantee ────────────────────────────────────────────────
assert_no_grep "E: no request recorded anywhere mentions ntfy.sh" "ntfy.sh" "$E_SINK_LOG"
e_all_args="$(cat "$TEST_TMP"/e_args*.txt 2>/dev/null || true)"
assert_empty_str "E: the fake CLI was never asked to send anything outward" \
  "$(printf '%s' "$e_all_args" | grep -iE 'curl |ntfy\.sh|git push' || true)"
