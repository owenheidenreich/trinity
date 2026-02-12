#!/bin/bash
# ============================================================================
# Bulk-delete old Docker Hub tags for gdubx/trinity-inference
# Keeps: latest, v4-intelligence
# Deletes: everything else (all v2-* timestamps, v3-*, v4-debug, etc.)
# ============================================================================

REPO="gdubx/trinity-inference"
KEEP_TAGS="latest v4-intelligence"

echo "=== Docker Hub Tag Cleanup ==="
echo "Repository: $REPO"
echo "Keeping: $KEEP_TAGS"
echo ""

# Get Docker Hub token using Docker Desktop credentials
echo "Authenticating with Docker Hub..."
echo -n "Docker Hub username [gdubx]: "
read -r USERNAME
USERNAME=${USERNAME:-gdubx}

echo -n "Docker Hub password or Personal Access Token: "
read -rs PASSWORD
echo ""

TOKEN=$(curl -s -X POST "https://hub.docker.com/v2/users/login/" \
  -H "Content-Type: application/json" \
  -d "{\"username\": \"$USERNAME\", \"password\": \"$PASSWORD\"}" | \
  python3 -c "import sys,json; print(json.load(sys.stdin).get('token',''))" 2>/dev/null)

if [ -z "$TOKEN" ]; then
    echo "ERROR: Authentication failed. Check username/password."
    echo "Tip: Create a Personal Access Token at https://hub.docker.com/settings/security"
    exit 1
fi
echo "✓ Authenticated"

# Collect ALL tags across all pages
echo ""
echo "Fetching all tags..."
ALL_TAGS=""
PAGE=1
while true; do
    RESPONSE=$(curl -s "https://hub.docker.com/v2/repositories/$REPO/tags/?page_size=100&page=$PAGE" \
      -H "Authorization: Bearer $TOKEN")
    
    TAGS=$(echo "$RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for t in data.get('results', []):
    print(t['name'])
" 2>/dev/null)
    
    if [ -z "$TAGS" ]; then
        break
    fi
    
    ALL_TAGS="$ALL_TAGS
$TAGS"
    
    NEXT=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('next','') or '')" 2>/dev/null)
    if [ -z "$NEXT" ]; then
        break
    fi
    PAGE=$((PAGE + 1))
done

# Filter out tags we want to keep
DELETE_TAGS=""
DELETE_COUNT=0
KEEP_COUNT=0
while IFS= read -r tag; do
    [ -z "$tag" ] && continue
    SHOULD_KEEP=false
    for keep in $KEEP_TAGS; do
        if [ "$tag" = "$keep" ]; then
            SHOULD_KEEP=true
            break
        fi
    done
    if $SHOULD_KEEP; then
        echo "  KEEP: $tag"
        KEEP_COUNT=$((KEEP_COUNT + 1))
    else
        DELETE_TAGS="$DELETE_TAGS $tag"
        DELETE_COUNT=$((DELETE_COUNT + 1))
    fi
done <<< "$ALL_TAGS"

echo ""
echo "Tags to keep: $KEEP_COUNT"
echo "Tags to delete: $DELETE_COUNT"
echo ""

if [ "$DELETE_COUNT" -eq 0 ]; then
    echo "Nothing to delete!"
    exit 0
fi

echo -n "Proceed with deleting $DELETE_COUNT tags? [y/N]: "
read -r CONFIRM
if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
    echo "Aborted."
    exit 0
fi

# Delete tags
echo ""
DELETED=0
FAILED=0
for tag in $DELETE_TAGS; do
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE \
      "https://hub.docker.com/v2/repositories/$REPO/tags/$tag/" \
      -H "Authorization: Bearer $TOKEN")
    
    if [ "$HTTP_CODE" = "204" ]; then
        DELETED=$((DELETED + 1))
        # Progress every 10 deletions
        if [ $((DELETED % 10)) -eq 0 ]; then
            echo "  Deleted $DELETED / $DELETE_COUNT tags..."
        fi
    else
        echo "  FAILED ($HTTP_CODE): $tag"
        FAILED=$((FAILED + 1))
    fi
    
    # Small delay to avoid rate limiting
    sleep 0.1
done

echo ""
echo "=== Cleanup Complete ==="
echo "Deleted: $DELETED tags"
echo "Failed: $FAILED tags"
echo "Remaining: $KEEP_COUNT tags"
