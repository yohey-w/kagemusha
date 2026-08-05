#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# H. layer boundary — core must not depend on cookbook/.
#
# docs/layers.md states the norm in three lines: core ships shape and never
# content; setup.sh / core's scripts / core's templates must not read, copy,
# or execute anything under cookbook/; dependency is one-way. A norm stated
# only in prose is a norm nobody can see being broken — one added `cp` line
# and the sample shelf has silently become a default. This group measures it.
#
#   H1  manifests/scaffold.tsv is well-formed and carries ZERO cookbook/ refs
#   H2  SENTINEL: a string planted in every file on the shelf reaches nothing
#       setup.sh produces. This is the one check that measures the norm as a
#       BEHAVIOUR rather than as a property of the source text.
#   H3  INACTIVITY: what core scaffolds is empty FORM — zero active regexes,
#       zero principles, zero dated journal events, zero pending samples. A
#       template with a filled-in judgment in it is content shipped under the
#       name of shape, which is the failure this whole split exists to fix.
#   H4  setup.sh DRIVES its copies from the manifest (proved by changing the
#       manifest and watching the output change), the scaffolded tree matches
#       the manifest exactly, and the shelf's own files are absent from it.
#   H5  scripts/ and config.env.example carry ZERO RUNTIME dependency on
#       cookbook/ (a comment pointing readers at cookbook/README.md is fine)
#   H6  the cookbook/ shelf and the boundary declaration are structurally
#       present and agree with each other
# ═══════════════════════════════════════════════════════════════════════════
# shellcheck shell=bash
# shellcheck disable=SC2154  # globals come from scripts/test.sh

group "H. layer boundary (core must not depend on cookbook/)"

H_MANIFEST="$REPO_ROOT/manifests/scaffold.tsv"

# ─── H1. the scaffold manifest ─────────────────────────────────────────────
assert_file "H1: manifests/scaffold.tsv exists" "$H_MANIFEST"

H_ROWS="$TEST_TMP/h_rows.tsv"
grep -vE '^[[:space:]]*(#|$)' "$H_MANIFEST" > "$H_ROWS" 2>/dev/null || :
h_n="$(wc -l < "$H_ROWS" | tr -d ' ')"
# a floor: emptying the manifest must not buy a green run
assert_ge "H1: manifest carries its rows ($h_n found)" "$h_n" 10

# rule 5 first, and against the WHOLE file including comments: the one-way
# dependency rule is the reason this manifest exists at all.
assert_no_grep "H1: manifest contains no 'cookbook/' anywhere (one-way rule)" \
  "cookbook/" "$H_MANIFEST"

h_bad_fields=""; h_bad_source=""; h_bad_dest=""; h_dotdot=""
h_missing=""; h_dupe=""; h_seen=""
while IFS= read -r line; do
  [[ -n "$line" ]] || continue
  # rule 1: exactly 3 tab-separated fields
  n_fields="$(printf '%s' "$line" | awk -F'\t' '{print NF}')"
  if [[ "$n_fields" != "3" ]]; then
    h_bad_fields="${h_bad_fields}${line} (fields=${n_fields})"$'\n'; continue
  fi
  src="$(printf '%s' "$line" | cut -f1)"
  dst="$(printf '%s' "$line" | cut -f2)"
  grd="$(printf '%s' "$line" | cut -f3)"

  # rule 1 (cont.): no leading / trailing whitespace in any field
  for fld in "$src" "$dst" "$grd"; do
    case "$fld" in
      " "*|*" "|""|$'\t'*) h_bad_fields="${h_bad_fields}${line} (blank/padded field)"$'\n' ;;
    esac
  done

  # rule 2: source is relative and templates/-rooted
  case "$src" in
    templates/*) : ;;
    *) h_bad_source="${h_bad_source}${src}"$'\n' ;;
  esac
  case "$src" in /*) h_bad_source="${h_bad_source}${src} (absolute)"$'\n' ;; esac

  # rule 3: dest is relative
  case "$dst" in /*) h_bad_dest="${h_bad_dest}${dst} (absolute)"$'\n' ;; esac

  # rule 4: no '..' segment in any field
  case "/$src/$dst/$grd/" in */../*) h_dotdot="${h_dotdot}${line}"$'\n' ;; esac

  # rule 6: source exists in the repo
  [[ -f "$REPO_ROOT/$src" ]] || h_missing="${h_missing}${src}"$'\n'

  # rule 7: no duplicate dest
  case $'\n'"$h_seen" in *$'\n'"$dst"$'\n'*) h_dupe="${h_dupe}${dst}"$'\n' ;; esac
  h_seen="${h_seen}${dst}"$'\n'
done < "$H_ROWS"

assert_empty_str "H1: every row has exactly 3 non-padded tab-separated fields" "$h_bad_fields"
assert_empty_str "H1: every source is relative and rooted at templates/" "$h_bad_source"
assert_empty_str "H1: every dest is relative" "$h_bad_dest"
assert_empty_str "H1: no '..' path segment in any field" "$h_dotdot"
assert_empty_str "H1: every source file exists in the repo" "$h_missing"
assert_empty_str "H1: no duplicate dest" "$h_dupe"

# The old directional check ("every manifest source is named somewhere in
# setup.sh") is GONE on purpose, and its absence is not a gap. It existed only
# because the manifest was a hand-kept transcript of a copy list living inside
# the script; two lists kept in step by hand need a checker for the day someone
# edits one. There is now one list. setup.sh names no template at all, and H4
# proves it reads this file by changing the file and watching the output move —
# which is a stronger claim than "both files mention the same word".
assert_no_grep "H1: setup.sh keeps no second copy list (no template is named in it)" \
  "templates/decisions.md" "$REPO_ROOT/scripts/setup.sh"

# positive control: the checks above CAN see a violation
H_BAD="$TEST_TMP/h_bad.tsv"
printf 'cookbook/author/starter-disciplines.md\tjudgment/x.md\tskip-if-exists\n' > "$H_BAD"
assert_grep "H1: control — a planted cookbook/ source IS visible to grep" \
  "cookbook/" "$H_BAD"


# ─── H2. SENTINEL — nothing on the shelf reaches what setup.sh produces ────
# The strongest form of the norm is behavioural: plant a string that exists
# ONLY under the shelf, run the real scaffolder, and look for it in everything
# that came out. A source-text grep can be defeated by an indirection (a path
# assembled from two variables, a file read through a symlink); this cannot.
H_SENT="KAGEMUSHA_SHELF_SENTINEL_9d3f1a"
H2_FX="$TEST_TMP/h2_kit"
kit_copy "$H2_FX"
H_SHELF_DIR="$H2_FX/$(printf 'cook%s' 'book')"
assert_dir "H2: the shelf is present in the fixture (or the test proves nothing)" "$H_SHELF_DIR"

h2_planted=0
while IFS= read -r f; do
  printf '\n%s\n' "$H_SENT" >> "$f"
  h2_planted=$((h2_planted + 1))
done < <(find "$H_SHELF_DIR" -type f)
assert_ge "H2: the sentinel was planted in every file on the shelf" "$h2_planted" 5

H2_LOG="$TEST_TMP/h2_run.log"
"$H2_FX/scripts/setup.sh" > "$H2_LOG" 2>&1
assert_eq "H2: setup.sh still exits 0 with the shelf poisoned" "0" "$?"

# everything setup.sh produced = what exists now, minus the tracked kit itself
h2_tracked="$(git -C "$REPO_ROOT" ls-files | LC_ALL=C sort)"
h2_now="$( (cd "$H2_FX" && find . -type f | sed 's|^\./||') | LC_ALL=C sort)"
h2_created="$(comm -13 <(printf '%s\n' "$h2_tracked") <(printf '%s\n' "$h2_now"))"
assert_nonempty_str "H2: setup.sh created something to check" "$h2_created"

h2_hits=""
while IFS= read -r rel; do
  [[ -n "$rel" ]] || continue
  grep -qF -- "$H_SENT" "$H2_FX/$rel" && h2_hits="${h2_hits}${rel}"$'\n'
done <<< "$h2_created"
assert_empty_str "H2: no scaffolded file carries the shelf sentinel" "$h2_hits"

# …and none of them names the shelf either
h2_named=""
while IFS= read -r rel; do
  [[ -n "$rel" ]] || continue
  grep -qF -- "cookbook/" "$H2_FX/$rel" && h2_named="${h2_named}${rel}"$'\n'
done <<< "$h2_created"
assert_empty_str "H2: no scaffolded file names the shelf at all" "$h2_named"
assert_no_grep "H2: the run's own output does not name the sentinel" "$H_SENT" "$H2_LOG"

# control: the sentinel IS findable where it was planted, so an empty result
# above means "did not travel", not "was never there".
assert_grep "H2: control — the sentinel really is on the shelf" \
  "$H_SENT" "$H_SHELF_DIR/README.md"

# ─── H3. INACTIVITY — core's templates are FORM, with nothing filled in ────
# Core ships shape and never content (docs/layers.md, norm 1). "Content" here
# is not a vibe: it is a rule that would fire, a principle that would be read
# as adopted, a dated event that reads as history, a queue item that reads as
# work waiting. Each of those is counted, and the count must be zero.
H_T="$REPO_ROOT/templates"

# active = a line that is not blank and not a comment. grep -c exits 1 on a
# count of zero, which is the answer we are usually hoping for, so the exit
# code is swallowed and only the number kept.
h_active_lines() { grep -vcE '^[[:space:]]*(#|$)' "$1" 2>/dev/null || true; }

# h_section FILE HEADING — the lines of one '## ' section, up to the next one.
# Needed because a numbered list in a DIFFERENT section of the same file (the
# "how to grow a verifier" steps) looks exactly like a DoD entry to a regex.
h_section() {
  awk -v h="$2" 'index($0, h) == 1 { inside = 1; next }
                 /^## / { inside = 0 }
                 inside' "$1"
}

assert_eq "H3: the correction vocabulary ships with zero active patterns" \
  "0" "$(h_active_lines "$H_T/correction_patterns.example.txt")"
assert_eq "H3: the discipline catalog ships with zero entries" \
  "0" "$(grep -cE '^[[:space:]]*-[[:space:]]+id:' "$H_T/discipline_catalog.example.yaml" || true)"
assert_eq "H3: the judgment model ships with zero principles" \
  "0" "$(grep -cE '^[0-9]+\. \*\*' "$H_T/judgment_model.md" || true)"
assert_eq "H3: the journal ships with zero dated events" \
  "0" "$(grep -cE '^### D-[0-9]{4}-[0-9]{2}-[0-9]{2}' "$H_T/decisions_journal.md" || true)"
assert_eq "H3: the decisions SSOT ships with zero dated decisions" \
  "0" "$(grep -cE '^### D-[0-9]{4}-[0-9]{2}-[0-9]{2}' "$H_T/decisions.md" || true)"
assert_eq "H3: the approval queue ships with zero pending items" \
  "0" "$(grep -cE '^## Q-[0-9]{4}-[0-9]{2}-[0-9]{2}' "$H_T/approval_queue.md" || true)"
assert_eq "H3: the promotion queue ships with zero candidates" \
  "0" "$(grep -cE '^### C-[0-9]{4}-[0-9]{2}-[0-9]{2}' "$H_T/promotion_queue.md" || true)"
assert_eq "H3: the candidate format ships with zero candidates" \
  "0" "$(grep -cE '^### C-[0-9]{4}-[0-9]{2}-[0-9]{2}' "$H_T/promotion_candidate.md" || true)"
assert_eq "H3: verifiers ships with zero machine-layer rows" \
  "0" "$(grep -cE '^\| \*\*' "$H_T/verifiers.md" || true)"
assert_eq "H3: verifiers ships with zero DoD entries" \
  "0" "$(h_section "$H_T/verifiers.md" '## (B)' | grep -cE '^[0-9]+\. \*\*' || true)"
assert_eq "H3: the system map ships with zero project cards" \
  "0" "$(grep -cE '^### ' "$H_T/system_map.md" || true)"

# the SSOT tables ship with headers and no data rows. A data row is any table
# line that is neither the header nor its separator.
h_table_rows() {  # h_table_rows FILE — count DATA rows across every table
  # A data row is a table line that follows a |---|---| separator. The state
  # resets on any non-table line, so a second table's HEADER is not counted as
  # the first table's data, and a row inside an HTML comment is not counted
  # at all — a commented-out example is documentation, not content.
  awk '/^[[:space:]]*<!--/ { c = 1 }
       c { if (/-->/) c = 0; next }
       /^\|/ { if ($0 ~ /^\|[-| :]+$/) { sep = 1; next }
                if (sep) print
                next }
       { sep = 0 }' "$1" | wc -l | tr -d ' '
}
for h_f in tasks glossary people; do
  assert_eq "H3: ssot/$h_f ships with headers and zero data rows" \
    "0" "$(h_table_rows "$H_T/$h_f.md")"
done
assert_eq "H3: the decisions index ships with zero rows" \
  "0" "$(h_table_rows "$H_T/decisions.md")"

# no template carries a filled-in date where a form should carry a placeholder.
# YYYY-MM-DD and <...> are placeholders; a real date is a record.
h_dated=""
for h_f in decisions tasks glossary people approval_queue verifiers system_map \
           decisions_journal judgment_model promotion_queue promotion_candidate \
           charter agent_instructions; do
  grep -qE '20[0-9]{2}-[0-9]{2}-[0-9]{2}' "$H_T/$h_f.md" \
    && h_dated="${h_dated}${h_f}.md"$'\n'
done
assert_empty_str "H3: no core template carries a real calendar date" "$h_dated"

# control: the detectors above CAN see content — run them against a file that
# has some. A detector nobody has watched detect anything is not evidence.
H3_PROBE="$TEST_TMP/h3_probe.md"
printf '### D-2026-01-31-01 [topic: x]\n- 判断: y\n' > "$H3_PROBE"
assert_eq "H3: control — a dated event IS counted when present" \
  "1" "$(grep -cE '^### D-[0-9]{4}-[0-9]{2}-[0-9]{2}' "$H3_PROBE" || true)"
printf '| a | b |\n|---|---|\n| 1 | 2 |\n' > "$H3_PROBE"
assert_eq "H3: control — a table data row IS counted when present" \
  "1" "$(h_table_rows "$H3_PROBE")"

# ─── H4. setup.sh is DRIVEN by the manifest ────────────────────────────────
# Two claims, and the second is the one that matters: (a) what landed equals
# what the manifest says, and (b) setup.sh actually READ the manifest — proved
# by editing the manifest in a throwaway kit and watching the output follow.
H4_FX="$TEST_TMP/h4_kit"
kit_copy "$H4_FX"
"$H4_FX/scripts/setup.sh" > "$TEST_TMP/h4_run.log" 2>&1
assert_eq "H4: setup.sh exits 0" "0" "$?"

h4_expected="$( { cut -f2 "$H_ROWS"
                  # the two files setup.sh creates that are NOT manifest rows,
                  # named in the manifest's own "deliberately not" section
                  printf 'config.env\njudgment/correction_patterns.txt\n'
                } | LC_ALL=C sort)"
h4_tracked="$(git -C "$REPO_ROOT" ls-files | LC_ALL=C sort)"
h4_now="$( (cd "$H4_FX" && find . -type f | sed 's|^\./||') | LC_ALL=C sort)"
h4_created="$(comm -13 <(printf '%s\n' "$h4_tracked") <(printf '%s\n' "$h4_now"))"
assert_eq "H4: the scaffolded tree is exactly the manifest (plus the two named extras)" \
  "$h4_expected" "$h4_created"

# (b) the manifest is READ, not transcribed: add a row, and the file appears.
H4_FX2="$TEST_TMP/h4_kit2"
kit_copy "$H4_FX2"
printf 'templates/glossary.md\tssot/h4_probe.md\tskip-if-exists\n' \
  >> "$H4_FX2/manifests/scaffold.tsv"
"$H4_FX2/scripts/setup.sh" > "$TEST_TMP/h4_run2.log" 2>&1
assert_file "H4: a row added to the manifest is copied by setup.sh" \
  "$H4_FX2/ssot/h4_probe.md"
assert_same "H4: …from the source the row names" \
  "$H4_FX2/ssot/h4_probe.md" "$H4_FX2/templates/glossary.md"

# …and a row that breaks a validation rule is a hard stop, never a skipped line
h4_bad_row() {  # h4_bad_row ROW — fresh kit, append ROW, run, return exit code
  local row="$1" fx="$TEST_TMP/h4_bad_$2"
  kit_copy "$fx"
  printf '%s\n' "$row" >> "$fx/manifests/scaffold.tsv"
  "$fx/scripts/setup.sh" > "$TEST_TMP/h4_bad_$2.log" 2>&1
}
assert_exit "H4: a source outside templates/ is exit 2" 2 \
  h4_bad_row "$(printf 'lib/x.sh\tssot/x.md\tskip-if-exists')" a
assert_exit "H4: a '..' segment is exit 2" 2 \
  h4_bad_row "$(printf 'templates/../lib/x.sh\tssot/x.md\tskip-if-exists')" b
assert_exit "H4: an absolute dest is exit 2" 2 \
  h4_bad_row "$(printf 'templates/glossary.md\t/tmp/x.md\tskip-if-exists')" c
assert_exit "H4: a missing source is exit 2" 2 \
  h4_bad_row "$(printf 'templates/no_such_file.md\tssot/x.md\tskip-if-exists')" d
assert_exit "H4: a two-field row is exit 2" 2 \
  h4_bad_row "$(printf 'templates/glossary.md\tssot/x.md')" e
assert_exit "H4: an unknown guard is exit 2" 2 \
  h4_bad_row "$(printf 'templates/glossary.md\tssot/x.md\tclobber')" f

# the shelf's own files are absent from the manifest — asserted per name, since
# rule 5 already forbids the prefix and these would have to arrive some other way
# Checked against the DATA ROWS, not the whole file: the manifest's own
# "deliberately not in this manifest" section names some of these on purpose,
# and that paragraph is the record of the decision, not a violation of it.
h4_shelf_named=""
for h4_n in starter-disciplines evidence/ community/ reference-instance; do
  grep -qF -- "$h4_n" "$H_ROWS" && h4_shelf_named="${h4_shelf_named}${h4_n}"$'\n'
done
assert_empty_str "H4: no shelf file (starter disciplines, evidence, community, reference instance) is in the manifest" \
  "$h4_shelf_named"

# ─── H5. no runtime dependency from core's scripts on cookbook/ ────────────
# Allowed: a COMMENT that points the reader at cookbook/README.md. Anything
# else — a path in a variable, a cp, a source, a read — is a boundary breach.
H_CORE_FILES=()
while IFS= read -r f; do H_CORE_FILES+=("$f"); done < <(
  git -C "$REPO_ROOT" ls-files -- scripts config.env.example
)
assert_ge "H5: core runtime files found" "${#H_CORE_FILES[@]}" 8

# h_runtime_hits FILE... — print every cookbook/ line that is NOT an allowed
# comment reference. Empty output = clean.
h_runtime_hits() {
  local f line lineno
  for f in "$@"; do
    lineno=0
    while IFS= read -r line; do
      lineno=$((lineno + 1))
      case "$line" in *cookbook/*) : ;; *) continue ;; esac
      # allowed: comment line whose only mention is the README signpost
      if [[ "$line" =~ ^[[:space:]]*# ]] && [[ "$line" == *"cookbook/README.md"* ]]; then
        continue
      fi
      printf '%s:%s:%s\n' "$f" "$lineno" "$line"
    done < "$f"
  done
}

h_breach=""
for f in "${H_CORE_FILES[@]}"; do
  h_breach="${h_breach}$(h_runtime_hits "$REPO_ROOT/$f")"
done
assert_empty_str "H5: scripts/ and config.env.example carry no runtime cookbook/ dependency" \
  "$h_breach"

# positive control on the detector itself — a detector nobody has seen detect
# anything is not evidence (same rule as group C).
H_PROBE_DIR="$TEST_TMP/h_probe"
mkdir -p "$H_PROBE_DIR"
printf '#!/usr/bin/env bash\ncp "$ROOT/cookbook/author/starter-disciplines.md" "$T/d.md"\n' \
  > "$H_PROBE_DIR/breach.sh"
printf '#!/usr/bin/env bash\n# samples live in cookbook/README.md — copy one yourself\n' \
  > "$H_PROBE_DIR/ok.sh"
assert_nonempty_str "H5: control — a cp from cookbook/ IS flagged" \
  "$(h_runtime_hits "$H_PROBE_DIR/breach.sh")"
assert_empty_str "H5: control — a cookbook/README.md signpost comment is NOT flagged" \
  "$(h_runtime_hits "$H_PROBE_DIR/ok.sh")"

# setup.sh specifically: the scaffolder is the highest-risk file
assert_no_grep "H5: setup.sh never names cookbook/ at all" \
  "cookbook/" "$REPO_ROOT/scripts/setup.sh"

# ─── H6 (FRAME). the shelf and the boundary declaration are present ────────
# Widen this in the same step that enables H2-H4.
assert_file "H6: cookbook/README.md exists"           "$REPO_ROOT/cookbook/README.md"
assert_file "H6: cookbook/author/README.md exists"    "$REPO_ROOT/cookbook/author/README.md"
assert_file "H6: cookbook/community/README.md exists" "$REPO_ROOT/cookbook/community/README.md"
assert_file "H6: docs/layers.md exists"               "$REPO_ROOT/docs/layers.md"
assert_file "H6: docs/path-migrations.md exists"      "$REPO_ROOT/docs/path-migrations.md"

# the boundary declaration must actually declare the boundary
assert_grep "H6: layers.md states core must not read cookbook/" \
  "読み込んでも" "$REPO_ROOT/docs/layers.md"
assert_grep "H6: layers.md states the rule in English too" \
  "must not read, copy, or execute" "$REPO_ROOT/docs/layers.md"
assert_grep "H6: layers.md names the manifest as the enforcement point" \
  "manifests/scaffold.tsv" "$REPO_ROOT/docs/layers.md"

# the shelf README must NOT let 'cookbook/' read as a privacy boundary
assert_grep "H6: cookbook/README.md denies being a privacy boundary (EN)" \
  "not a privacy boundary" "$REPO_ROOT/cookbook/README.md"
assert_grep "H6: cookbook/README.md denies being a privacy boundary (JA)" \
  "プライバシー境界ではない" "$REPO_ROOT/cookbook/README.md"
assert_grep "H6: cookbook/README.md says the two layers share one git history" \
  "同一のリポジトリ・同一の履歴" "$REPO_ROOT/cookbook/README.md"

# author/ must separate 'it ran' / 'it was selected' / 'it may not fit you'
assert_grep "H6: author shelf states it is not a recommendation" \
  "推奨ではありません" "$REPO_ROOT/cookbook/author/README.md"

# community/ under cookbook/ is a signpost only while the bots still use the
# old prefix — it must say so, or people will file PRs into a dead lane
assert_grep "H6: cookbook/community/README.md points submissions at the live lane" \
  "まだ投稿先ではありません" "$REPO_ROOT/cookbook/community/README.md"

# the shelf is tracked by git — the allowlist .gitignore must un-ignore it, or
# the split would be uncommittable by the same construction that protects
# ssot/ and judgment/. Asserted per path, not as a count: a count would go
# green on any five files landing anywhere under either directory.
h_untracked=""
for p in cookbook/README.md cookbook/author/README.md cookbook/community/README.md \
         manifests/scaffold.tsv; do
  git -C "$REPO_ROOT" ls-files --error-unmatch -- "$p" >/dev/null 2>&1 \
    || h_untracked="${h_untracked}${p}"$'\n'
done
assert_empty_str "H6: the shelf and the manifest are tracked by git" "$h_untracked"
