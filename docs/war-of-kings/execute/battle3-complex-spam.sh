#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# ⚔️  WAR OF THREE KINGS - BATTLE 3: COMPLEX KNOWLEDGE SPAM ⚔️
# ═══════════════════════════════════════════════════════════════════════════════
#
# Ultimate stress test with complex reasoning questions under high load
# Tests: reasoning quality, stability under pressure, error handling
#
# Run: ./battle3-complex-spam.sh [qwen|llama|mixtral|all] [concurrency]
# Example: ./battle3-complex-spam.sh all 50
#
# ═══════════════════════════════════════════════════════════════════════════════

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="$SCRIPT_DIR/../results/raw"
TIMEOUT=120  # Longer timeout for complex reasoning

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
CYAN='\033[0;36m'
NC='\033[0m'

# ═══════════════════════════════════════════════════════════════════════════════
# COMPLEX KNOWLEDGE PROMPTS (Require multi-step reasoning)
# ═══════════════════════════════════════════════════════════════════════════════

declare -a COMPLEX_PROMPTS=(
    "A farmer has 17 sheep. All but 9 run away. Then he buys 5 more sheep, sells half of what he has, and 3 more sheep run away. How many sheep does he have now? Show your work step by step."
    
    "Write a Python function that finds the longest palindromic substring in a given string. Include time complexity analysis."
    
    "Explain the CAP theorem and give a real-world example of a system that sacrifices consistency for availability. Then explain when this tradeoff makes sense."
    
    "A bat and ball cost \$1.10. The bat costs \$1 more than the ball. What does the ball cost? Now, if I have 10 bats and 10 balls, and I give away 3 bats to someone who pays me the cost of 2 balls for each bat, how much money do I have in total?"
    
    "Write a recursive function in Python to generate all valid combinations of n pairs of parentheses. Explain why the time complexity is related to Catalan numbers."
    
    "Three people check into a hotel room that costs \$30. They each pay \$10. Later, the manager realizes the room should only cost \$25 and gives \$5 to the bellboy to return. The bellboy keeps \$2 and gives \$1 back to each person. Now each person paid \$9, totaling \$27. The bellboy has \$2. That's only \$29. Where is the missing dollar?"
    
    "Implement a thread-safe singleton pattern in Python. Explain why the naive implementation is not thread-safe and how your solution fixes it."
    
    "You have 8 identical-looking balls. One is slightly heavier. You have a balance scale and can only use it twice. How do you find the heavy ball? Explain your reasoning."
    
    "Design a rate limiter that allows 100 requests per minute per user. Explain the token bucket vs sliding window approaches and implement one in Python."
    
    "Prove that the sum of the first n odd numbers equals n² using mathematical induction. Show the base case, inductive hypothesis, and inductive step clearly."
    
    "Write a Python function to detect a cycle in a linked list using Floyd's algorithm. Explain why it works with the mathematical proof."
    
    "Explain the Byzantine Generals Problem and how Practical Byzantine Fault Tolerance (PBFT) solves it. What's the minimum number of nodes needed to tolerate f failures?"
    
    "Implement a trie data structure in Python with insert, search, and startsWith methods. What's the time complexity of each operation?"
    
    "A train leaves Chicago at 9am going 60mph. Another train leaves New York (780 miles away) at 10am going 80mph toward Chicago. At what time do they meet? Show calculations."
    
    "Write a Python function to find the kth largest element in an unsorted array in O(n) average time. Explain the quickselect algorithm."
    
    "Explain how RSA encryption works at a high level. Why is it computationally infeasible to break? What role do prime numbers play?"
    
    "You have 12 coins, one is counterfeit (either heavier or lighter). Using a balance scale exactly 3 times, identify the counterfeit and whether it's heavier or lighter."
    
    "Implement merge sort in Python with detailed comments explaining each step. What makes it stable? Why is it preferred for linked lists?"
    
    "Explain the difference between optimistic and pessimistic locking in databases. When would you use each? Give examples."
    
    "Write a Python function to serialize and deserialize a binary tree. Handle null nodes properly. What's the time and space complexity?"
)

# ═══════════════════════════════════════════════════════════════════════════════
# FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

single_complex_request() {
    local url=$1
    local model=$2
    local prompt=$3
    local request_id=$4
    local output_file=$5
    
    local start=$(date +%s.%N)
    
    local response=$(curl -s -w "\n===CURL_STATS===\nhttp_code:%{http_code}\ntime_total:%{time_total}\nsize_download:%{size_download}" \
        --max-time $TIMEOUT \
        -X POST "$url/generate" \
        -H "Content-Type: application/json" \
        -d "{
            \"model\": \"$model\",
            \"prompt\": \"$prompt\",
            \"stream\": false,
            \"options\": {
                \"num_predict\": 2000,
                \"temperature\": 0.3
            }
        }" 2>&1)
    
    local end=$(date +%s.%N)
    local elapsed=$(echo "$end - $start" | bc)
    
    # Parse stats
    local http_code=$(echo "$response" | grep "http_code:" | cut -d: -f2)
    local curl_time=$(echo "$response" | grep "time_total:" | cut -d: -f2)
    local size=$(echo "$response" | grep "size_download:" | cut -d: -f2)
    local body=$(echo "$response" | sed '/===CURL_STATS===/,$d')
    
    # Extract response and token counts if available
    local answer=$(echo "$body" | grep -o '"response":"[^"]*"' | sed 's/"response":"//;s/"$//' 2>/dev/null | head -c 3000 || echo "ERROR")
    local eval_count=$(echo "$body" | grep -o '"eval_count":[0-9]*' | cut -d: -f2 || echo "0")
    local prompt_eval_count=$(echo "$body" | grep -o '"prompt_eval_count":[0-9]*' | cut -d: -f2 || echo "0")
    
    # Calculate tokens per second
    local tps="0"
    if [[ "$eval_count" != "0" && "$curl_time" != "0" ]]; then
        tps=$(echo "scale=2; $eval_count / $curl_time" | bc 2>/dev/null || echo "0")
    fi
    
    # Write full output
    cat >> "$output_file" << EOF
{"id":$request_id,"http":"$http_code","time":$curl_time,"elapsed":$elapsed,"size":$size,"eval_tokens":${eval_count:-0},"prompt_tokens":${prompt_eval_count:-0},"tps":$tps,"answer_preview":"$(echo "$answer" | head -c 200 | tr -d '\n' | tr '"' "'" )"}
EOF
    
    if [[ "$http_code" == "200" ]]; then
        echo -n "${GREEN}.${NC}"
        return 0
    else
        echo -n "${RED}x${NC}"
        return 1
    fi
}

export -f single_complex_request
export TIMEOUT
export GREEN RED NC

run_complex_spam() {
    local king_name=$1
    local king_url=$2
    local king_model=$3
    local concurrency=$4
    local emoji=$5
    
    local output_dir="$RESULTS_DIR/$king_name/battle3-complex"
    mkdir -p "$output_dir"
    
    local num_requests=$concurrency  # One request per concurrent slot for max stress
    local output_file="$output_dir/complex_c${concurrency}_$(date +%Y%m%d_%H%M%S).jsonl"
    
    echo ""
    echo "───────────────────────────────────────────────────────────────"
    echo "$emoji $king_name @ Concurrency $concurrency (COMPLEX)"
    echo "   Requests: $num_requests complex reasoning tasks"
    echo "   Timeout: ${TIMEOUT}s per request"
    echo "   Output: $output_file"
    echo "───────────────────────────────────────────────────────────────"
    
    > "$output_file"
    
    local start_time=$(date +%s.%N)
    
    # Fire ALL requests simultaneously for maximum stress
    echo -n "   Progress: "
    for i in $(seq 1 $num_requests); do
        local prompt_idx=$((($i - 1) % ${#COMPLEX_PROMPTS[@]}))
        local prompt="${COMPLEX_PROMPTS[$prompt_idx]}"
        
        single_complex_request "$king_url" "$king_model" "$prompt" "$i" "$output_file" &
    done
    
    wait
    echo ""
    
    local end_time=$(date +%s.%N)
    local total_time=$(echo "$end_time - $start_time" | bc)
    
    # Analyze results
    local success=$(grep -c '"http":"200"' "$output_file" 2>/dev/null || echo 0)
    local fail=$((num_requests - success))
    local success_rate=$(echo "scale=1; $success / $num_requests * 100" | bc)
    
    # Token stats
    local total_tokens=$(grep -o '"eval_tokens":[0-9]*' "$output_file" | cut -d: -f2 | awk '{sum+=$1} END {print sum}')
    local avg_tps=$(echo "scale=2; ${total_tokens:-0} / $total_time" | bc 2>/dev/null || echo "0")
    
    # Timing stats
    local times=$(grep -o '"time":[0-9.]*' "$output_file" | cut -d: -f2 | sort -n)
    local avg_time=$(echo "$times" | awk '{sum+=$1} END {if(NR>0) printf "%.2f", sum/NR; else print "0"}')
    local min_time=$(echo "$times" | head -1)
    local max_time=$(echo "$times" | tail -1)
    
    echo ""
    echo "   📊 RESULTS:"
    echo "   ─────────────────────────────────────────"
    echo "   ✅ Success: $success/$num_requests ($success_rate%)"
    echo "   ❌ Failed: $fail"
    echo "   ⏱️  Total wall time: ${total_time}s"
    echo "   📈 Avg response time: ${avg_time}s"
    echo "   📈 Fastest: ${min_time:-N/A}s | Slowest: ${max_time:-N/A}s"
    echo "   🔤 Total tokens generated: ${total_tokens:-0}"
    echo "   ⚡ Aggregate tokens/sec: $avg_tps"
    
    # Write summary
    cat > "$output_dir/summary_c${concurrency}.json" << EOF
{
    "king": "$king_name",
    "battle": "Complex Knowledge Spam",
    "concurrency": $concurrency,
    "total_requests": $num_requests,
    "successful": $success,
    "failed": $fail,
    "success_rate": $success_rate,
    "total_time_seconds": $total_time,
    "avg_response_time": $avg_time,
    "min_response_time": "${min_time:-null}",
    "max_response_time": "${max_time:-null}",
    "total_tokens": ${total_tokens:-0},
    "tokens_per_second": $avg_tps,
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
    echo "$emoji BATTLE 3: COMPLEX KNOWLEDGE SPAM - $king_name"
    echo "═══════════════════════════════════════════════════════════════"
    echo "This battle tests reasoning quality under maximum pressure."
    echo "All requests fire simultaneously - true stress test!"
    
    # Progressive stress levels - all concurrent
    for conc in 10 25 50; do
        run_complex_spam "$king_name" "$king_url" "$king_model" "$conc" "$emoji"
        echo ""
        echo "   ⏸️  5 second cooldown..."
        sleep 5
    done
    
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo "$emoji $king_name BATTLE 3 COMPLETE"
    echo "═══════════════════════════════════════════════════════════════"
}

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║    ⚔️  WAR OF THREE KINGS - BATTLE 3: COMPLEX SPAM ⚔️             ║"
echo "║           THE STRONGEST MAN - Maximum Pressure Test              ║"
echo "║                     $(date +%H:%M:%S)                                   ║"
echo "╚══════════════════════════════════════════════════════════════════╝"

KING="${1:-all}"
CONCURRENCY="${2:-}"

case "$KING" in
    qwen)
        if [ -n "$CONCURRENCY" ]; then
            run_complex_spam "qwen" "$QWEN_URL" "$QWEN_MODEL" "$CONCURRENCY" "👑"
        else
            run_full_battle "qwen" "$QWEN_URL" "$QWEN_MODEL" "👑"
        fi
        ;;
    llama)
        if [ -n "$CONCURRENCY" ]; then
            run_complex_spam "llama" "$LLAMA_URL" "$LLAMA_MODEL" "$CONCURRENCY" "🦙"
        else
            run_full_battle "llama" "$LLAMA_URL" "$LLAMA_MODEL" "🦙"
        fi
        ;;
    mixtral)
        if [ -n "$CONCURRENCY" ]; then
            run_complex_spam "mixtral" "$MIXTRAL_URL" "$MIXTRAL_MODEL" "$CONCURRENCY" "🔮"
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
        echo "  $0 all              # Full battle, all kings, stress levels 10/25/50"
        echo "  $0 qwen 50          # Single test: Qwen at 50 concurrent complex"
        exit 1
        ;;
esac

echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo "BATTLE 3 COMPLETE - Results: $RESULTS_DIR/*/battle3-complex/"
echo "═══════════════════════════════════════════════════════════════════"
