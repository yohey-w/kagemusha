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
# WHAT IS ACTIVE NOW (the additive phase — cookbook/ has been added, nothing
# has been switched over yet):
#   H1  manifests/scaffold.tsv is well-formed and carries ZERO cookbook/ refs
#   H5  scripts/ and config.env.example carry ZERO RUNTIME dependency on
#       cookbook/ (a comment pointing readers at cookbook/README.md is fine)
#   H6  the cookbook/ shelf and the boundary declaration are structurally
#       present and agree with each other
#
# NOT YET ACTIVE — do not read their absence as a pass:
#   H2  sentinel: a planted cookbook/ reference in a scaffold path is caught
#   H3  inactivity: `rm -rf cookbook/` leaves the full suite green
#   H4  setup.sh drives its copies from the manifest, and the scaffolded tree
#       matches the manifest exactly (setup.sh does NOT read the manifest yet
#       — the file is currently a hand-kept transcript of what it does)
# H2-H4 are enabled in the step that changes setup.sh and switches the paths
# over. Enabling them here would either fail on purpose or assert nothing.
#
# H6 is a FRAME. It asserts the subset that can be true in the additive
# phase; its final scope is fixed by the acceptance list in the ruling that
# designed this split, and should be widened in the same step as H2-H4.
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

# the manifest is a transcript of setup.sh; if setup.sh stops copying a
# template the transcript has to notice. Cheap directional check: every
# source named here is mentioned somewhere in setup.sh.
h_unclaimed=""
while IFS= read -r src; do
  base="${src#templates/}"
  grep -qF -- "${base%.md}" "$REPO_ROOT/scripts/setup.sh" || h_unclaimed="${h_unclaimed}${src}"$'\n'
done < <(cut -f1 "$H_ROWS")
assert_empty_str "H1: every manifest source is still referenced by setup.sh" "$h_unclaimed"

# positive control: the checks above CAN see a violation
H_BAD="$TEST_TMP/h_bad.tsv"
printf 'cookbook/author/starter-disciplines.md\tjudgment/x.md\tskip-if-exists\n' > "$H_BAD"
assert_grep "H1: control — a planted cookbook/ source IS visible to grep" \
  "cookbook/" "$H_BAD"

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
