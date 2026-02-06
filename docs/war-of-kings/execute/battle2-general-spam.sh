#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# ⚔️  WAR OF THREE KINGS - BATTLE 2: GENERAL KNOWLEDGE SPAM ⚔️
# ═══════════════════════════════════════════════════════════════════════════════
#
# High-rate stress test with simple general knowledge questions
# Tests throughput, latency, and stability under load
#
# Run: ./battle2-general-spam.sh [qwen|llama|mixtral|all] [concurrency]
# Example: ./battle2-general-spam.sh qwen 25
#
# ═══════════════════════════════════════════════════════════════════════════════

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="$SCRIPT_DIR/../results/raw"
TIMEOUT=60

# King endpoints
QWEN_URL="https://sptj5nup2lc939i2h4bhq532gs.ingress.quanglong.org"
LLAMA_URL="http://56oqg7o6n9fu53ijan3udmmb5o.ingress.h4i-dedicated.eu-sw-2.digitalfrontier.so"
MIXTRAL_URL="https://bnivii01v9bcbchrqtej5pmd0k.ingress.4090.akashgpu.com"

QWEN_MODEL="qwen2.5:72b"
LLAMA_MODEL="llama3.3:70b"
MIXTRAL_MODEL="mixtral:8x22b"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# ═══════════════════════════════════════════════════════════════════════════════
# GENERAL KNOWLEDGE PROMPTS (Simple, fast responses expected)
# ═══════════════════════════════════════════════════════════════════════════════

declare -a GENERAL_PROMPTS=(
    "What is 2 + 2? Answer with just the number."
    "What is the capital of France? One word answer."
    "What color is the sky on a clear day? One word."
    "How many days are in a week? Just the number."
    "What is the opposite of hot? One word."
    "Name any mammal. One word."
    "What number comes after 9? Just the number."
    "Is water wet? Yes or no."
    "What season comes after summer? One word."
    "How many legs does a dog have? Just the number."
    "What planet do we live on? One word."
    "What is 10 x 10? Just the number."
    "What color is grass? One word."
    "How many months in a year? Just the number."
    "What is the largest ocean? One word."
    "Is the sun a star? Yes or no."
    "What is 50 divided by 2? Just the number."
    "Name the largest continent. One word."
    "How many hours in a day? Just the number."
    "What is frozen water called? One word."
)

# ═══════════════════════════════════════════════════════════════════════════════
# FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

single_request() {
    local url=$1
    local model=$2
    local prompt=$3
    local request_id=$4
    local output_file=$5
    
    local start=$(date +%s.%N)
    
    local response=$(curl -s -w "\n%{http_code}\n%{time_total}" --max-time $TIMEOUT \
        -X POST "$url/generate" \
        -H "Content-Type: application/json" \
        -d "{
            \"model\": \"$model\",
            \"prompt\": \"$prompt\",
            \"stream\": false,
            \"options\": {\"num_predict\": 50, \"temperature\": 0.1}
        }" 2>&1)
    
    local end=$(date +%s.%N)
    
    # Parse response parts
    local curl_time=$(echo "$response" | tail -n1)
    local http_code=$(echo "$response" | tail -n2 | head -n1)
    local body=$(echo "$response" | head -n -2)
    
    # Extract response text
    local answer=$(echo "$body" | grep -o '"response":"[^"]*"' | sed 's/"response":"//;s/"$//' 2>/dev/null || echo "ERROR")
    
    # Write to output
    echo "{\"id\":$request_id,\"http\":\"$http_code\",\"time\":$curl_time,\"answer\":\"$(echo $answer | head -c 100 | tr -d '\n')\"}" >> "$output_file"
    
    # Return success/fail
    if [[ "$http_code" == "200" ]]; then
        return 0
    else
        return 1
    fi
}

export -f single_request

run_spam_test() {
    local king_name=$1
    local king_url=$2
    local king_model=$3
    local concurrency=$4
    local emoji=$5
    
    local output_dir="$RESULTS_DIR/$king_name/battle2-general"
    mkdir -p "$output_dir"
    
    local requests_per_level=$((concurrency * 2))  # 2 requests per concurrent slot
    local output_file="$output_dir/spam_c${concurrency}_$(date +%Y%m%d_%H%M%S).jsonl"
    
    echo ""
    echo "───────────────────────────────────────────────────────────────"
    echo "$emoji $king_name @ Concurrency $concurrency"
    echo "   Requests: $requests_per_level"
    echo "   Output: $output_file"
    echo "───────────────────────────────────────────────────────────────"
    
    # Clear output file
    > "$output_file"
    
    local start_time=$(date +%s.%N)
    local success=0
    local fail=0
    
    # Generate requests and run in parallel
    for i in $(seq 1 $requests_per_level); do
        local prompt_idx=$((($i - 1) % ${#GENERAL_PROMPTS[@]}))
        local prompt="${GENERAL_PROMPTS[$prompt_idx]}"
        
        # Run in background with semaphore pattern
        while [ $(jobs -r | wc -l) -ge $concurrency ]; do
            sleep 0.1
        done
        
        (single_request "$king_url" "$king_model" "$prompt" "$i" "$output_file" && echo -n "." || echo -n "x") &
    done
    
    # Wait for all to complete
    wait
    echo ""
    
    local end_time=$(date +%s.%N)
    local total_time=$(echo "$end_time - $start_time" | bc)
    
    # Count results
    success=$(grep -c '"http":"200"' "$output_file" 2>/dev/null || echo 0)
    fail=$((requests_per_level - success))
    
    # Calculate metrics
    local success_rate=$(echo "scale=1; $success / $requests_per_level * 100" | bc)
    local rps=$(echo "scale=2; $success / $total_time" | bc)
    
    # Extract timing stats
    local times=$(grep -o '"time":[0-9.]*' "$output_file" | sed 's/"time"://' | sort -n)
    local avg_time=$(echo "$times" | awk '{sum+=$1} END {if(NR>0) printf "%.3f", sum/NR; else print "0"}')
    local p50=$(echo "$times" | awk 'NR==int(FNR*0.5)+1{print}')
    local p95=$(echo "$times" | awk 'NR==int(FNR*0.95)+1{print}')
    
    echo "   ✅ Success: $success/$requests_per_level ($success_rate%)"
    echo "   ❌ Failed: $fail"
    echo "   ⏱️  Total time: ${total_time}s"
    echo "   📊 Requests/sec: $rps"
    echo "   📈 Avg latency: ${avg_time}s"
    echo "   📈 P50 latency: ${p50:-N/A}s"
    echo "   📈 P95 latency: ${p95:-N/A}s"
    
    # Write summary
    cat > "$output_dir/summary_c${concurrency}.json" << EOF
{
    "king": "$king_name",
    "battle": "General Knowledge Spam",
    "concurrency": $concurrency,
    "total_requests": $requests_per_level,
    "successful": $success,
    "failed": $fail,
    "success_rate": $success_rate,
    "total_time_seconds": $total_time,
    "requests_per_second": $rps,
    "avg_latency": $avg_time,
    "p50_latency": "${p50:-null}",
    "p95_latency": "${p95:-null}",
    "timestamp": "$(date -Iseconds)"
}
EOF
}

run_full_battle() {
    local king_name=$1
    local king_url=$2
    local king_model=$3
    local emoji=$4
    
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo "$emoji BATTLE 2: GENERAL KNOWLEDGE SPAM - $king_name"
    echo "═══════════════════════════════════════════════════════════════"
    
    # Progressive concurrency levels
    for conc in 5 10 25 50; do
        run_spam_test "$king_name" "$king_url" "$king_model" "$conc" "$emoji"
        sleep 2  # Brief pause between levels
    done
    
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo "$emoji $king_name BATTLE 2 COMPLETE"
    echo "═══════════════════════════════════════════════════════════════"
}

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║     ⚔️  WAR OF THREE KINGS - BATTLE 2: GENERAL SPAM ⚔️            ║"
echo "║                     $(date +%H:%M:%S)                                   ║"
echo "╚══════════════════════════════════════════════════════════════════╝"

KING="${1:-all}"
CONCURRENCY="${2:-}"

case "$KING" in
    qwen)
        if [ -n "$CONCURRENCY" ]; then
            run_spam_test "qwen" "$QWEN_URL" "$QWEN_MODEL" "$CONCURRENCY" "👑"
        else
            run_full_battle "qwen" "$QWEN_URL" "$QWEN_MODEL" "👑"
        fi
        ;;
    llama)
        if [ -n "$CONCURRENCY" ]; then
            run_spam_test "llama" "$LLAMA_URL" "$LLAMA_MODEL" "$CONCURRENCY" "🦙"
        else
            run_full_battle "llama" "$LLAMA_URL" "$LLAMA_MODEL" "🦙"
        fi
        ;;
    mixtral)
        if [ -n "$CONCURRENCY" ]; then
            run_spam_test "mixtral" "$MIXTRAL_URL" "$MIXTRAL_MODEL" "$CONCURRENCY" "🔮"
        else
            run_full_battle "mixtral" "$MIXTRAL_URL" "$MIXTRAL_MODEL" "🔮"
        fi
        ;;
    all)
        run_full_battle "qwen" "$QWEN_URL" "$QWEN_MODEL" "👑"
        run_full_battle "llama" "$LLAMA_URL" "$LLAMA_MODEL" "🦙"
        run_full_battle "mixtral" "$MIXTRAL_URL" "$MIXTRAL_MODEL" "🔮"
        ;;
    *)
        echo "Usage: $0 [qwen|llama|mixtral|all] [concurrency]"
        echo ""
        echo "Examples:"
        echo "  $0 all              # Full battle, all kings, all concurrency levels"
        echo "  $0 qwen 25          # Single test: Qwen at 25 concurrent"
        exit 1
        ;;
esac

echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo "BATTLE 2 COMPLETE - Results: $RESULTS_DIR/*/battle2-general/"
echo "═══════════════════════════════════════════════════════════════════"
