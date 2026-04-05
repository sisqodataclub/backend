#!/bin/bash

# Exit immediately if a command fails
set -e

# Automatically detect which branch you are currently on
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)

echo "📦 Preparing to ship code to branch: [$CURRENT_BRANCH]"

# Check if there are actually any changes to commit
if [ -z "$(git status --porcelain)" ]; then
    echo "🤷‍♂️ No changes detected. Your working directory is clean!"
    exit 0
fi

# If you didn't provide a message when running the script, it will ask you for one
if [ -z "$1" ]; then
    read -p "📝 Enter your commit message: " COMMIT_MSG
else
    COMMIT_MSG="$1"
fi

# Ensure the commit message isn't completely empty
if [ -z "$COMMIT_MSG" ]; then
    echo "❌ Error: You must provide a commit message. Aborting."
    exit 1
fi

echo "🧹 Staging all files (respecting your .gitignore)..."
git add .

echo "💾 Committing with message: '$COMMIT_MSG'..."
git commit -m "$COMMIT_MSG"

echo "🚀 Pushing to GitHub (origin/$CURRENT_BRANCH)..."
git push origin "$CURRENT_BRANCH"

echo "====================================================="
echo "✅ Code successfully shipped to GitHub!"
echo "====================================================="
