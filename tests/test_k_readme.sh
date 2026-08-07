#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# K. the README contract — the front door is a budget, not a canvas.
#
# A README grows by one well-meant paragraph at a time until nobody reads any
# of it. So the five jobs it has (say what this is · say who it is for · hand
# over one safe run · point at the evidence and its limits · route to the right
# document) are held by a machine budget: line counts, one code block, no
# images beyond the CI badge, and a canonical section frozen against a fixture.
#
# Two things are asserted that are NOT about size:
#   · every intra-README link resolves to a heading that exists. The frozen
#     canonical section links out to three of them — rename one and the
#     immutable section breaks silently.
#   · the English and Japanese files carry the same contract blocks in the same
#     order. Sameness of ORDER, never of wording or line count: the two files
#     are translations, not copies, and a diff-based check would freeze the
#     prose of both.
#
# What is deliberately NOT frozen (see the verdict this group implements):
# counts that legitimately move — "N places to distil into", the file table,
# the tool list, external CLI commands, how many runs there have been.
# ═══════════════════════════════════════════════════════════════════════════
# shellcheck shell=bash
# shellcheck disable=SC2154  # globals come from scripts/test.sh

group "K. README contract (the front door stays thin)"

K_EN="$REPO_ROOT/README.md"
K_JA="$REPO_ROOT/README_ja.md"

assert_file "K: README.md exists" "$K_EN"
assert_file "K: README_ja.md exists" "$K_JA"

# k_nonblank FILE — the unit every budget in this group is counted in.
k_nonblank() { grep -cve '^[[:space:]]*$' "$1" || true; }

# k_between FILE START END — the lines strictly between two marker lines.
k_between() { awk -v a="$2" -v b="$3" 'index($0,a){f=1;next} index($0,b){f=0} f' "$1"; }

for k_f in "$K_EN" "$K_JA"; do
  k_name="$(basename "$k_f")"

  # ── the budgets ──────────────────────────────────────────────────────────
  k_total="$(k_nonblank "$k_f")"
  if [[ "$k_total" -le 150 ]]; then pass "K: $k_name is at most 150 non-blank lines ($k_total)"
  else fail "K: $k_name is at most 150 non-blank lines" "got $k_total.
The front door has five jobs (identity · fit · one safe run · evidence and its
limits · routing). Anything else belongs in docs/ — see docs/README.md."; fi

  assert_grep "K: $k_name has a porch start marker" "<!-- porch:start -->" "$k_f"
  assert_grep "K: $k_name has a porch end marker" "<!-- porch:end -->" "$k_f"
  k_porch="$(k_between "$k_f" '<!-- porch:start -->' '<!-- porch:end -->' | grep -cve '^[[:space:]]*$' || true)"
  if [[ "$k_porch" -ge 5 && "$k_porch" -le 32 ]]; then
    pass "K: $k_name porch is 5-32 non-blank lines ($k_porch)"
  else
    fail "K: $k_name porch is 5-32 non-blank lines" "got $k_porch — the porch must fit one screen with no scrolling"
  fi

  # ── the bans ─────────────────────────────────────────────────────────────
  k_h2="$(grep -c '^## ' "$k_f" || true)"
  assert_ge "K: $k_name has at most 7 H2 sections (got $k_h2)" 7 "$k_h2"

  # exactly one fenced code block: the demo. Two fence lines, no more.
  k_fence="$(grep -c '^```' "$k_f" || true)"
  assert_eq "K: $k_name carries exactly one fenced code block (the demo)" "2" "$k_fence"

  # images: the CI badge is the one allowed image, so it is excluded by name
  k_img="$(grep -n '!\[' "$k_f" | grep -vc 'badge\.svg' || true)"
  assert_eq "K: $k_name carries no image other than the CI badge" "0" "$k_img"
  assert_eq "K: $k_name carries no mermaid diagram" "0" "$(grep -c 'mermaid' "$k_f" || true)"
  assert_eq "K: $k_name carries no <details> block" "0" "$(grep -c '<details' "$k_f" || true)"

  # ── the canonical section: exactly one, and frozen ───────────────────────
  assert_eq "K: $k_name carries the canonical heading exactly once" \
    "1" "$(grep -c '^### 訂正の昇格$' "$k_f" || true)"

  # ── the evidence tag is the same in both files ───────────────────────────
  assert_grep "K: $k_name names the fixed evidence tag" "evidence-v1.0.0" "$k_f"

  # ── the floor: a budget with only a ceiling can be met by an empty page ──
  # So the porch is checked for the four things it exists to carry. Presence,
  # never wording — except the one line that IS the project's claim, which is
  # quoted elsewhere and has to keep saying the same thing.
  k_porch_txt="$TEST_TMP/k_porch_$k_name.txt"
  k_between "$k_f" '<!-- porch:start -->' '<!-- porch:end -->' > "$k_porch_txt"

  assert_grep "K: $k_name porch carries the brand line" \
    "$([[ "$k_name" == "README_ja.md" ]] && echo '判断の中身は配らない。形だけ配る。' || echo 'We ship the forms')" \
    "$k_porch_txt"

  # who it is for, and who it is not — both halves, or the reader cannot self-select
  k_fit_yes="$([[ "$k_name" == "README_ja.md" ]] && echo '**向く人**' || echo '**Fits**')"
  k_fit_no="$([[ "$k_name" == "README_ja.md" ]] && echo '**向かない人**' || echo '**Does not fit**')"
  assert_grep "K: $k_name porch says who it fits" "$k_fit_yes" "$k_porch_txt"
  assert_grep "K: $k_name porch says who it does NOT fit" "$k_fit_no" "$k_porch_txt"

  # the three ways in: the frozen evidence, the demo, the install
  assert_grep "K: $k_name porch links the fixed evidence" "tree/evidence-v1.0.0" "$k_porch_txt"
  assert_grep "K: $k_name porch links the demo page" "docs/getting-started.md#" "$k_porch_txt"
  k_entries="$(grep -oE '\]\((docs/[^)]*|https://github\.com/[^)]*tree/evidence-v[^)]*)\)' "$k_porch_txt" | wc -l | tr -d ' ')"
  if [[ "$k_entries" -ge 3 && "$k_entries" -le 4 ]]; then
    pass "K: $k_name porch offers 3-4 ways in (got $k_entries)"
  else
    fail "K: $k_name porch offers 3-4 ways in" "got $k_entries — the porch hands over three entrances, not a link farm"
  fi

  # and the one command that makes it real, inside a fence, inside the porch
  assert_grep "K: $k_name porch carries the runnable demo command" \
    "./scripts/demo-distillation.sh" "$k_porch_txt"
  assert_eq "K: $k_name porch's demo sits in a fenced block" \
    "2" "$(grep -c '^```' "$k_porch_txt" || true)"

  # ── the routing index actually routes: six destinations, all of them real ──
  k_routes="$TEST_TMP/k_routes_$k_name.txt"
  awk 'index($0,"<!-- contract:routes -->"){f=1;next} index($0,"<!-- contract:field-record -->"){f=0} f' "$k_f" > "$k_routes"
  k_missing_route=""
  for k_dest in docs/getting-started.md docs/operations.md docs/design.md \
                docs/layers.md docs/judgment-distillation.md docs/README.md; do
    grep -qF -- "($k_dest)" "$k_routes" || k_missing_route="${k_missing_route}${k_dest}"$'\n'
  done
  assert_empty_str "K: $k_name routes to all six destinations" "$k_missing_route"
done

# ── the canon block matches its fixture, byte for byte ─────────────────────
# Frozen against a fixture rather than a hash so a failure prints a diff: this
# is the one section of the repository that must mean the same thing wherever
# it is quoted, so an edit has to be a deliberate act, never a drive-by.
for k_pair in "README.md:canon_correction_promotion_en.md" "README_ja.md:canon_correction_promotion_ja.md"; do
  k_f="$REPO_ROOT/${k_pair%%:*}"
  k_fx="$TESTS_DIR/fixtures/${k_pair##*:}"
  k_got="$TEST_TMP/k_canon_$(basename "$k_f").md"
  k_between "$k_f" '<!-- canon:correction-promotion:start -->' '<!-- canon:correction-promotion:end -->' > "$k_got"
  assert_file "K: canon fixture exists for $(basename "$k_f")" "$k_fx"
  assert_same "K: $(basename "$k_f") canonical section is unchanged (frozen)" "$k_fx" "$k_got"
done

# ── English and Japanese carry the same contract blocks, in the same order ──
K_WANT_ORDER="identity
demo
evidence
boundary
canon
routes
field-record"
k_order() { grep -o '<!-- contract:[a-z-]* -->' "$1" | sed 's/<!-- contract:\(.*\) -->/\1/'; }
assert_eq "K: README.md declares the seven contract blocks in order" \
  "$K_WANT_ORDER" "$(k_order "$K_EN")"
assert_eq "K: README_ja.md declares the same blocks in the same order" \
  "$(k_order "$K_EN")" "$(k_order "$K_JA")"

# ── the commercial lane: one article, one book, in one block ───────────────
# Not "no commerce" — the rule is that it lives in one place, below the fold,
# and never as the first thing a reader is asked to do.
for k_f in "$K_EN" "$K_JA"; do
  k_name="$(basename "$k_f")"
  k_zenn="$(grep -o 'zenn\.dev' "$k_f" | wc -l | tr -d ' ')"
  assert_eq "K: $k_name links Zenn at most twice (one article, one book)" "2" "$k_zenn"
  k_fr="$(awk 'index($0,"<!-- contract:field-record -->"){f=1} f' "$k_f" | grep -o 'zenn\.dev' | wc -l | tr -d ' ')"
  assert_eq "K: $k_name keeps both Zenn links inside the field-record block" "2" "$k_fr"
  assert_empty_str "K: $k_name quotes no price and no urgency" \
    "$(grep -nEi '(¥|\$[0-9]|[0-9]+ ?円|今すぐ|完全版|続きは有料|buy now|full version)' "$k_f" || true)"
done

# ── every link resolves ────────────────────────────────────────────────────
# The frozen canonical section links to three headings inside the README and to
# its counterpart file. This is the assertion that keeps a rename from silently
# breaking a section CI otherwise guarantees is immutable.
K_LINKCHECK="$TEST_TMP/k_linkcheck.py"
cat > "$K_LINKCHECK" <<'PYEOF'
import re, sys, os, unicodedata

def slug(h):
    h = re.sub(r'`|\*|_', '', h.strip()).lower()
    out = []
    for ch in h:
        cat = unicodedata.category(ch)
        if cat[0] in 'LNM':
            out.append(ch)
        elif ch in ' \t-':
            out.append('-')
    return ''.join(out)

def headings(path):
    return {slug(re.sub(r'^#{1,6}\s+', '', l))
            for l in open(path, encoding='utf-8').read().split('\n')
            if re.match(r'^#{1,6} ', l)}

root = sys.argv[1]
bad = []
for f in sys.argv[2:]:
    p = os.path.join(root, f)
    own = headings(p)
    for m in re.finditer(r'\]\(([^)\s]+)\)', open(p, encoding='utf-8').read()):
        t = m.group(1)
        if t.startswith(('http://', 'https://', 'mailto:')):
            continue
        path, _, frag = t.partition('#')
        # relative links resolve against the linking FILE's directory
        target = os.path.normpath(os.path.join(os.path.dirname(p), path)) if path else p
        if path and not os.path.exists(target):
            bad.append(f'{f}: missing file: {t}')
            continue
        if frag and slug(frag) not in (own if not path else headings(target)):
            bad.append(f'{f}: missing anchor: {t}')
print('\n'.join(bad))
PYEOF
assert_empty_str "K: every link in both READMEs resolves (file and anchor)" \
  "$(python3 "$K_LINKCHECK" "$REPO_ROOT" README.md README_ja.md)"

# ── and every other tracked markdown file, too ─────────────────────────────
# The READMEs were the reason this checker exists, but a shipped kit whose
# sample shelf links into nowhere is the same defect one directory down — and
# it had been there for months, unmeasured, because nothing was measuring.
#
# tests/fixtures/ is excluded BY CONSTRUCTION, not by convenience: those files
# are byte-identical copies of a README fragment, so their links are relative
# to the repository root and "fixing" them would break the freeze they exist
# to hold. (The community lane's own format lint rejects `../` outright, so a
# contributed shelf cannot add a relative link that lands here.)
K_ALL_MD=()
while IFS= read -r f; do
  case "$f" in tests/fixtures/*) continue ;; esac
  K_ALL_MD+=("$f")
done < <(git -C "$REPO_ROOT" ls-files '*.md')
assert_ge "K: tracked markdown files to link-check" "${#K_ALL_MD[@]}" 40
assert_empty_str "K: every link in every tracked markdown file resolves" \
  "$(python3 "$K_LINKCHECK" "$REPO_ROOT" "${K_ALL_MD[@]}")"

# control: the link checker CAN see a broken link
K_PROBE_DIR="$TEST_TMP/k_probe"; mkdir -p "$K_PROBE_DIR"
printf '# t\n\n[a](#no-such-heading)\n[b](docs/no_such_file.md)\n' > "$K_PROBE_DIR/README.md"
assert_nonempty_str "K: control — a broken anchor and a missing file ARE reported" \
  "$(python3 "$K_LINKCHECK" "$K_PROBE_DIR" README.md)"

# control: the budget counter CAN see an over-budget file
printf 'x\n%.0s' {1..151} > "$K_PROBE_DIR/long.md"
assert_ge "K: control — the non-blank counter counts a 151-line file" \
  "$(k_nonblank "$K_PROBE_DIR/long.md")" 151

# ── the entry exam lives somewhere a contributor will meet it ──────────────
assert_grep "K: the README entry exam is stated in CONTRIBUTING" \
  "README 入場審査" "$REPO_ROOT/.github/CONTRIBUTING.md"
