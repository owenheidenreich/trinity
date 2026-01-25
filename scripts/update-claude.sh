#!/bin/bash
# CLAUDE.md Update Workflow Script
# Run after completing development tasks to update documentation

set -e

echo "📝 CLAUDE.md Update Workflow"
echo "============================"

# Get current branch and commit info
BRANCH=$(git branch --show-current)
LAST_COMMIT=$(git log -1 --oneline)

echo "Current branch: $BRANCH"
echo "Last commit: $LAST_COMMIT"
echo ""

# Check if CLAUDE.md has been modified
if git diff --name-only | grep -q "docs/CLAUDE.md"; then
    echo "✅ CLAUDE.md has been modified in this session"
else
    echo "⚠️  CLAUDE.md has not been modified. Consider updating status indicators."
    echo ""
    read -p "Do you want to edit CLAUDE.md now? (y/n): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Opening CLAUDE.md for editing..."
        # Note: This would open in editor, but we'll just show the path
        echo "Please edit: docs/CLAUDE.md"
        echo "Then run this script again."
        exit 0
    fi
fi

echo "📋 CLAUDE.md Status Update Checklist:"
echo "1. ✅ Updated completion status indicators (COMPLETE/IN PROGRESS/PLANNED)"
echo "2. ✅ Added implementation notes for completed features"
echo "3. ✅ Updated version numbers and timestamps"
echo "4. ✅ Verified all references are still accurate"
echo ""

read -p "Have you completed the checklist above? (y/n): " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🎉 CLAUDE.md update complete!"
    echo ""
    echo "Next steps:"
    echo "1. Commit your code changes"
    echo "2. Commit CLAUDE.md updates with a message like:"
    echo "   'docs: update CLAUDE.md status for [feature name]'"
    echo ""
    echo "Example commit message:"
    echo "git commit -m 'docs: mark Phase 5 Filecoin Archive as COMPLETE'"
else
    echo "Please complete the checklist and run this script again."
fi