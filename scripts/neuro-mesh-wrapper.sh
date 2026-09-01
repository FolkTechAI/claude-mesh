#!/bin/bash
# neuro-mesh: Mac-side wrapper for Neuro to run claude-mesh commands
# 
# Install to /Users/michaelfolk/bin/neuro-mesh (or integrate into existing ~/bin/neuro)
#
# Usage from Grok Bot box (via registered-computer Shell tool):
#   Shell(command='neuro-mesh send --message "Task claimed" --to claude-mac')
#   Shell(command='neuro-mesh drain --format=ftai')
#
# This wrapper runs claude-mesh on Mac as the neuro-grokbot peer.

export CLAUDE_MESH_PEER=neuro-grokbot

# Optional: Set mesh group if not using default project .claude-mesh config
# export CLAUDE_MESH_GROUP=mac-neuro-mesh

exec claude-mesh "$@"
