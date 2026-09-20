#!/bin/sh
# Stub Claude Code CLI: echoes back the prompt argument, prefixed, to prove
# `run_claude_code` wired argv/stdout correctly.
# Expected invocation: fake_claude_ok.sh -p "<task>" --output-format text [...]
echo "done: $2"
exit 0
