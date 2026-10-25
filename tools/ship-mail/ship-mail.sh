#!/usr/bin/env bash
# scripts/ship-mail.sh
# ship-mail — file-based mailbox bus between ship sessions (pilot).
# Spec: docs/specs/ship-mail-pilot.md
#
# Delivery = one atomic file write into the recipient's inbox directory.
# Zero model turns, zero daemons, zero journal: the files are the truth.
#
# Usage:
#   ship-mail.sh send --to <sid> --from <sid> [--title <t>] [--ref <r>] (--file <path> | --text <msg>)
#   ship-mail.sh inbox <sid>                     # list unread (count + one line per letter)
#   ship-mail.sh show <sid> [<filename>]         # print letter(s); without name — all unread
#   ship-mail.sh ack <sid> <filename>|all        # move letter(s) to read/
#   ship-mail.sh status <sid>                    # unread/read counts
#
# Exit codes:
#   0 ok · 1 usage/sanity · 2 body or letter file missing · 3 duplicate (idempotency)
#   4 address not in peer-registry (INC-18: ids from chat are not canonical)
#   5 registry file missing/unreadable
#
# Env:
#   SHIP_MAIL_HOME     mailbox root (default ~/.local/share/ship-mail)
#   SHIP_MAIL_REGISTRY peer-registry path (default OpenCode-Vault peer-registry.md)

set -euo pipefail

MAIL_HOME="${SHIP_MAIL_HOME:-$HOME/.local/share/ship-mail}"
REGISTRY="${SHIP_MAIL_REGISTRY:-$HOME/Projects/OpenCode-Vault/04-Memory/peer-registry.md}"

fail() {
  local code="${2:-1}"
  echo "ship-mail: $1" >&2
  exit "$code"
}

usage() {
  sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
  exit 1
}

# Sanity: a session id is ses_<alnum>; anything else is not addressable here.
sid_sane() {
  case "$1" in
    ses_[A-Za-z0-9]*) return 0 ;;
    *) return 1 ;;
  esac
}

registry_check() {
  local sid="$1" role="$2"
  sid_sane "$sid" || fail "$role '$sid' is not a session id (ses_...)" 1
  [[ -r "$REGISTRY" ]] || fail "registry not readable: $REGISTRY" 5
  grep -q "$sid" "$REGISTRY" || \
    fail "$role '$sid' not in peer-registry — register the session first (INC-18)" 4
}

# Quote a string as a YAML double-quoted scalar.
yaml_str() {
  local s="$1"
  s=${s//\\/\\\\}
  s=${s//\"/\\\"}
  printf '"%s"' "$s"
}

inbox_dir() {
  printf '%s/inbox/%s' "$MAIL_HOME" "$1"
}

# cmd_send --to SID --from SID [--title T] [--ref R] (--file F | --text MSG)
cmd_send() {
  local to="" from="" title="letter" ref="" text="" src=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --to) to="$2"; shift 2 ;;
      --from) from="$2"; shift 2 ;;
      --title) title="$2"; shift 2 ;;
      --ref) ref="$2"; shift 2 ;;
      --file) src="$2"; shift 2 ;;
      --text) text="$2"; shift 2 ;;
      *) fail "send: unknown option '$1'" 1 ;;
    esac
  done
  [[ -n "$to" && -n "$from" ]] || fail "send: --to and --from are required" 1
  if [[ -n "$text" && -n "$src" ]]; then fail "send: --text XOR --file, not both" 1; fi
  if [[ -z "$text" && -z "$src" ]]; then fail "send: --text or --file required" 1; fi

  registry_check "$to" "recipient"
  registry_check "$from" "sender"

  local body
  if [[ -n "$src" ]]; then
    [[ -r "$src" ]] || fail "source file not readable: $src" 2
    body="$(cat "$src")"
  else
    body="$text"
  fi

  # Idempotency: same body + sender + day = same id (as peer-comms letter.sh).
  local id ts dir fname tmpf
  id="$(printf '%s' "$body$from$(date +%F)" | sha256sum | cut -d' ' -f1)"
  id="${id:0:12}"
  ts="$(date +%Y-%m-%dT%H:%M:%S%:z)"
  dir="$(inbox_dir "$to")"
  mkdir -p "$dir/read"
  if compgen -G "$dir/*_${id}__*" >/dev/null || compgen -G "$dir/read/*_${id}__*" >/dev/null; then
    fail "duplicate letter id=$id (same body+sender+day already delivered)" 3
  fi

  fname="$(date +%Y%m%dT%H%M%S)_${id}__${from}.md"
  tmpf="$dir/.tmp.$$"
  {
    printf -- '---\n'
    printf 'type: Letter\n'
    printf 'from: %s\n' "$from"
    printf 'to: %s\n' "$to"
    printf 'title: '
    yaml_str "$title"
    printf '\n'
    if [[ -n "$ref" ]]; then
      printf 'ref: '
      yaml_str "$ref"
      printf '\n'
    fi
    printf 'ts: %s\n' "$ts"
    printf 'id: %s\n' "$id"
    printf -- '---\n'
    printf '%s\n' "$body"
  } > "$tmpf"
  mv "$tmpf" "$dir/$fname"
  echo "DELIVERED $dir/$fname"
}

# Unread letters of a session, sorted, one path per line (glob-safe).
unread_files() {
  local dir
  dir="$(inbox_dir "$1")"
  [[ -d "$dir" ]] || return 0
  find "$dir" -maxdepth 1 -type f -name '*.md' | sort
}

frontmatter_field() {
  # $1=file, $2=field; values are plain or YAML-quoted, we print them raw.
  sed -n "s/^$2: //p" "$1" | head -1
}

cmd_inbox() {
  local sid="$1" count=0 f from title
  sid_sane "$sid" || fail "'$sid' is not a session id" 1
  while IFS= read -r f; do
    count=$((count + 1))
  done < <(unread_files "$sid")
  echo "unread: $count"
  while IFS= read -r f; do
    from="$(frontmatter_field "$f" from)"
    title="$(frontmatter_field "$f" title)"
    printf '%s  %s  %s\n' "$(basename "$f")" "$from" "$title"
  done < <(unread_files "$sid")
}

cmd_show() {
  local sid="$1" want="${2:-}" f first=0
  sid_sane "$sid" || fail "'$sid' is not a session id" 1
  if [[ -n "$want" ]]; then
    local dir fpath
    dir="$(inbox_dir "$sid")"
    fpath="$dir/$want"
    [[ -f "$fpath" ]] || fail "no such letter: $want" 2
    cat "$fpath"
    return 0
  fi
  while IFS= read -r f; do
    if [[ $first -eq 1 ]]; then echo; fi
    echo "===== $(basename "$f")"
    cat "$f"
    first=1
  done < <(unread_files "$sid")
}

cmd_ack() {
  local sid="$1" what="$2" dir f moved=0
  sid_sane "$sid" || fail "'$sid' is not a session id" 1
  dir="$(inbox_dir "$sid")"
  mkdir -p "$dir/read"
  if [[ "$what" == "all" ]]; then
    while IFS= read -r f; do
      mv "$f" "$dir/read/$(basename "$f")"
      moved=$((moved + 1))
    done < <(unread_files "$sid")
  else
    [[ -f "$dir/$what" ]] || fail "no such letter: $what" 2
    mv "$dir/$what" "$dir/read/$what"
    moved=1
  fi
  echo "ACK $moved"
}

cmd_status() {
  local sid="$1" unread=0 read=0 dir
  sid_sane "$sid" || fail "'$sid' is not a session id" 1
  dir="$(inbox_dir "$sid")"
  while IFS= read -r _; do unread=$((unread + 1)); done < <(unread_files "$sid")
  if [[ -d "$dir/read" ]]; then
    read=$(find "$dir/read" -maxdepth 1 -type f -name '*.md' | wc -l)
  fi
  echo "unread: $unread"
  echo "read: $read"
}

main() {
  case "${1:-}" in
    send) shift; cmd_send "$@" ;;
    inbox) shift; [[ -n "${1:-}" ]] || fail "inbox: session id required" 1; cmd_inbox "$1" ;;
    show) shift; [[ -n "${1:-}" ]] || fail "show: session id required" 1; cmd_show "$@" ;;
    ack) shift; [[ -n "${1:-}" && -n "${2:-}" ]] || fail "ack: session id and filename|all required" 1; cmd_ack "$@" ;;
    status) shift; [[ -n "${1:-}" ]] || fail "status: session id required" 1; cmd_status "$1" ;;
    *) usage ;;
  esac
}

main "$@"
