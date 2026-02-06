#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# ⚔️  WAR OF THREE KINGS - OVERNIGHT STRESS TEST ⚔️
# ═══════════════════════════════════════════════════════════════════════════════
#
# 5-HOUR ENDURANCE TEST
# - Phase 1: 2.5 hours of BASIC questions (higher rate, won't crash connection)
# - Phase 2: 2.5 hours of COMPLEX questions (lower rate, intensive reasoning)
#
# ALL responses saved to disk. Think later. Analyze later.
# Every single response captured - errors, full text, timing, everything.
#
# Usage:
#   nohup ./overnight-stress.sh > overnight.log 2>&1 &
#
# Monitor:
#   tail -f overnight.log
#   watch "ls -la ../results/overnight/run_*/stats/"
#
# ═══════════════════════════════════════════════════════════════════════════════

# NOTE: Do NOT use 'set -e' - we want to continue even when requests fail!
# Every failure is captured in JSON for later analysis.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_BASE="$SCRIPT_DIR/../results/overnight"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RESULTS_DIR="$RESULTS_BASE/run_$TIMESTAMP"

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION - Tuned to avoid crashing connections
# ═══════════════════════════════════════════════════════════════════════════════

# Duration in seconds (2.5 hours each = 9000 seconds)
PHASE1_DURATION=9000   # 2.5 hours BASIC
PHASE2_DURATION=9000   # 2.5 hours COMPLEX

# Request intervals (seconds between requests PER KING)
# BASIC: 1 request every 10 seconds = 6/min = 900 per 2.5hr per king = 2700 total
# COMPLEX: 1 request every 45 seconds = 1.3/min = 200 per 2.5hr per king = 600 total
BASIC_INTERVAL=10
COMPLEX_INTERVAL=45

# Timeouts (generous to capture slow responses rather than fail)
BASIC_TIMEOUT=60
COMPLEX_TIMEOUT=180

# King endpoints
QWEN_URL="https://sptj5nup2lc939i2h4bhq532gs.ingress.quanglong.org"
LLAMA_URL="http://56oqg7o6n9fu53ijan3udmmb5o.ingress.h4i-dedicated.eu-sw-2.digitalfrontier.so"
MIXTRAL_URL="https://bnivii01v9bcbchrqtej5pmd0k.ingress.4090.akashgpu.com"

QWEN_MODEL="qwen2.5:72b"
LLAMA_MODEL="llama3.3:70b"
MIXTRAL_MODEL="mixtral:8x22b"

# ═══════════════════════════════════════════════════════════════════════════════
# BASIC PROMPTS - 50 simple questions (cycle through)
# ═══════════════════════════════════════════════════════════════════════════════

BASIC_PROMPTS=(
    "What is 2 + 2?"
    "What is the capital of France?"
    "What color is the sky on a clear day?"
    "How many days are in a week?"
    "What is the opposite of hot?"
    "Name a mammal."
    "What number comes after 9?"
    "Is water wet? Yes or no."
    "What season comes after summer?"
    "How many legs does a dog have?"
    "What planet do we live on?"
    "What is 10 multiplied by 10?"
    "What color is grass?"
    "How many months in a year?"
    "What is the largest ocean?"
    "Is the sun a star? Yes or no."
    "What is 50 divided by 2?"
    "Name the largest continent."
    "How many hours in a day?"
    "What is frozen water called?"
    "What is 7 + 8?"
    "Name any fruit."
    "What animal says moo?"
    "How many sides does a triangle have?"
    "What is the opposite of up?"
    "Name a primary color."
    "What day comes after Monday?"
    "How many cents in a dollar?"
    "Is ice hot or cold?"
    "What do bees make?"
    "What is 100 minus 1?"
    "Name any bird."
    "What do fish breathe in?"
    "How many wheels on a bicycle?"
    "What is the opposite of dark?"
    "Name a vegetable."
    "What is 5 times 5?"
    "How many fingers on one hand?"
    "What color is snow?"
    "What animal has a trunk?"
    "What is 20 + 20?"
    "Name any country."
    "What do cows drink?"
    "How many seconds in a minute?"
    "What is the opposite of fast?"
    "Name a tool."
    "What is 8 minus 3?"
    "How many weeks in a year approximately?"
    "What color is a ripe banana?"
    "Name any sport."
)

# ═══════════════════════════════════════════════════════════════════════════════
# COMPLEX PROMPTS - 30 reasoning challenges (cycle through)
# ═══════════════════════════════════════════════════════════════════════════════

COMPLEX_PROMPTS=(
    "A farmer has 17 sheep. All but 9 run away. Then he buys 5 more sheep, sells half of what he has, and 3 more sheep run away. How many sheep does he have now? Show your work step by step."
    "Write a Python function to find the longest palindromic substring in a given string. Include time complexity analysis and explain your approach."
    "Explain the CAP theorem in distributed systems. Give a real-world example of a system that sacrifices consistency for availability, and explain when this tradeoff makes sense."
    "A bat and a ball cost one dollar and ten cents together. The bat costs one dollar more than the ball. What does the ball cost? Explain why most people get this wrong initially."
    "Write a recursive function in Python to generate all valid combinations of n pairs of parentheses. Explain why the time complexity is related to Catalan numbers."
    "Three people check into a hotel room that costs thirty dollars. They each pay ten dollars. Later, the manager realizes the room should only cost twenty-five dollars and gives five dollars to the bellboy to return. The bellboy keeps two dollars and gives one dollar back to each person. Now each person paid nine dollars, totaling twenty-seven dollars. The bellboy has two dollars. That is only twenty-nine dollars. Where is the missing dollar? Explain the logical fallacy."
    "Implement a thread-safe singleton pattern in Python. Explain why the naive implementation using a simple class variable is not thread-safe and how your solution fixes it."
    "You have 8 identical-looking balls. One is slightly heavier than the others. You have a balance scale and can only use it twice. How do you find the heavy ball? Explain your complete reasoning."
    "Design a rate limiter that allows 100 requests per minute per user. Explain the token bucket algorithm versus the sliding window approach, and implement one in Python."
    "Prove that the sum of the first n odd numbers equals n squared using mathematical induction. Show the base case, inductive hypothesis, and inductive step clearly."
    "Implement Floyd's cycle detection algorithm for linked lists in Python. Explain why it works with the mathematical proof involving the tortoise and hare."
    "Explain the Byzantine Generals Problem and how Practical Byzantine Fault Tolerance (PBFT) solves it. What is the minimum number of nodes needed to tolerate f failures?"
    "Implement a Trie data structure in Python with insert, search, and startsWith methods. What is the time complexity of each operation and why?"
    "A train leaves Chicago at 9am going 60 miles per hour. Another train leaves New York (780 miles away) at 10am going 80 miles per hour toward Chicago. At what time do they meet? Show your calculations."
    "Write a Python function to find the kth largest element in an unsorted array in O(n) average time. Explain the quickselect algorithm and why it achieves this complexity."
    "Explain how RSA encryption works at a high level. Why is it computationally infeasible to break? What role do prime numbers play in its security?"
    "You have 12 identical-looking coins. One is counterfeit and is either heavier or lighter than the rest. Using a balance scale exactly 3 times, identify the counterfeit coin and determine whether it is heavier or lighter."
    "Implement merge sort in Python with detailed comments explaining each step. What makes merge sort stable? Why is it often preferred for sorting linked lists over arrays?"
    "Explain the difference between optimistic and pessimistic locking in database systems. When would you use each approach? Give concrete examples."
    "Write Python functions to serialize and deserialize a binary tree. Handle null nodes properly. What is the time and space complexity of your solution?"
    "Explain Godel's First Incompleteness Theorem in simple terms that a non-mathematician could understand. What does it mean for the foundations of mathematics?"
    "Explain the P versus NP problem. Give an example of an NP-complete problem and explain why it matters whether P equals NP."
    "Explain why the halting problem is undecidable. Sketch the proof by contradiction that Alan Turing used."
    "Sally has 3 brothers. Each brother has 2 sisters. How many sisters does Sally have? Explain why this question trips people up."
    "How many times does the letter r appear in the word strawberry? Count carefully and explain why large language models often fail this type of question."
    "Write a Python class implementing an LRU cache with O(1) time complexity for both get and put operations. You may use OrderedDict or implement your own solution."
    "Explain the difference between strong consistency and eventual consistency in distributed systems. When would you choose each approach?"
    "What is the Monty Hall problem? Should you switch doors? Prove your answer using probability theory."
    "Write a binary search function in Python that returns the index of the FIRST occurrence of the target value, correctly handling duplicate values."
    "Explain the pigeonhole principle. Use it to prove that in any group of 13 people, at least 2 must share a birthday month."
)

# ═══════════════════════════════════════════════════════════════════════════════
# UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

setup_directories() {
    mkdir -p "$RESULTS_DIR/qwen/basic"
    mkdir -p "$RESULTS_DIR/qwen/complex"
    mkdir -p "$RESULTS_DIR/llama/basic"
    mkdir -p "$RESULTS_DIR/llama/complex"
    mkdir -p "$RESULTS_DIR/mixtral/basic"
    mkdir -p "$RESULTS_DIR/mixtral/complex"
    mkdir -p "$RESULTS_DIR/stats"
    mkdir -p "$RESULTS_DIR/errors"
    mkdir -p "$RESULTS_DIR/raw"  # Raw response backup
    
    # Initialize master event log
    MASTER_LOG="$RESULTS_DIR/master_event_log.jsonl"
    touch "$MASTER_LOG"
    
    log "Created results directory structure: $RESULTS_DIR"
    log "Master event log: $MASTER_LOG"
}

# ═══════════════════════════════════════════════════════════════════════════════
# CORE REQUEST FUNCTION - Captures EVERYTHING (Moon Landing Edition)
# ═══════════════════════════════════════════════════════════════════════════════

send_request() {
    local king=$1
    local url=$2
    local model=$3
    local prompt=$4
    local phase=$5
    local request_num=$6
    local timeout=$7
    local output_dir=$8
    
    local timestamp=$(date +%Y%m%d_%H%M%S_%N)
    local output_file="$output_dir/${request_num}_${timestamp}.json"
    local raw_file="$RESULTS_DIR/raw/${king}_${phase}_${request_num}_${timestamp}.raw"
    local error_file="$RESULTS_DIR/errors/${king}_${phase}_${request_num}_${timestamp}.err"
    
    local start_time=$(date +%s.%N)
    local start_iso=$(date -Iseconds)
    
    # Escape prompt for JSON (bulletproof method)
    local escaped_prompt=$(printf '%s' "$prompt" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))' 2>/dev/null || echo "\"${prompt//\"/\\\"}\"")
    
    # Build the request payload and save it
    local request_payload="{
        \"model\": \"$model\",
        \"prompt\": $escaped_prompt,
        \"stream\": false,
        \"options\": {
            \"num_predict\": 2000,
            \"temperature\": 0.3
        }
    }"
    
    # Make request capturing ALL data including errors
    local response
    local curl_exit_code=0
    
    response=$(curl -s -w '\n___CURL_STATS___\n{"http_code":"%{http_code}","time_total":%{time_total},"time_connect":%{time_connect},"time_starttransfer":%{time_starttransfer},"size_download":%{size_download},"speed_download":%{speed_download}}' \
        --max-time "$timeout" \
        -X POST "$url/generate" \
        -H "Content-Type: application/json" \
        -d "$request_payload" 2>"$error_file") || curl_exit_code=$?
    
    local end_time=$(date +%s.%N)
    local end_iso=$(date -Iseconds)
    local elapsed=$(echo "$end_time - $start_time" | bc 2>/dev/null || echo "0")
    
    # ALWAYS save raw response first (before any parsing)
    echo "$response" > "$raw_file"
    
    # Parse response - split by our marker
    local curl_stats=""
    local body=""
    
    if echo "$response" | grep -q "___CURL_STATS___"; then
        curl_stats=$(echo "$response" | sed -n '/___CURL_STATS___/,$ p' | tail -1)
        body=$(echo "$response" | sed '/___CURL_STATS___/,$ d')
    else
        body="$response"
        curl_stats='{"http_code":"000","time_total":0,"error":"no_stats"}'
    fi
    
    # Handle empty body
    if [ -z "$body" ] || [ "$body" = "null" ]; then
        body='{"error":"empty_response"}'
    fi
    
    # Validate body is JSON, if not wrap it safely
    if ! echo "$body" | python3 -c "import json,sys; json.load(sys.stdin)" 2>/dev/null; then
        # Body is not valid JSON - escape it as a string
        local escaped_body=$(printf '%s' "$body" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))' 2>/dev/null || echo '"parse_error"')
        body="{\"raw_text\": $escaped_body, \"parse_error\": true}"
    fi
    
    # Check for curl errors
    local stderr_content=""
    if [ -s "$error_file" ]; then
        stderr_content=$(cat "$error_file" | tr '\n' ' ' | tr '"' "'" | tr -d '\r')
    else
        rm -f "$error_file" 2>/dev/null
    fi
    
    # Extract HTTP code for logging
    local http_code=$(echo "$curl_stats" | grep -o '"http_code":"[^"]*"' | cut -d'"' -f4 || echo "000")
    
    # Write comprehensive JSON output
    cat > "$output_file" << JSONEOF
{
    "meta": {
        "king": "$king",
        "model": "$model",
        "phase": "$phase",
        "request_num": $request_num,
        "timestamp": "$timestamp",
        "start_time": "$start_iso",
        "end_time": "$end_iso",
        "elapsed_seconds": $elapsed,
        "timeout_setting": $timeout,
        "curl_exit_code": ${curl_exit_code:-0},
        "http_code": "$http_code",
        "raw_file": "$raw_file"
    },
    "request": {
        "url": "$url/generate",
        "payload": $request_payload
    },
    "prompt": $escaped_prompt,
    "ollama_response": $body,
    "curl_stats": $curl_stats,
    "stderr": "$stderr_content"
}
JSONEOF

    # Append to master event log (JSONL format - one event per line)
    local status="success"
    [ "$http_code" != "200" ] && status="failed"
    echo "{\"ts\":\"$start_iso\",\"king\":\"$king\",\"phase\":\"$phase\",\"req\":$request_num,\"http\":\"$http_code\",\"elapsed\":$elapsed,\"status\":\"$status\"}" >> "$MASTER_LOG"

    # Progress indicator
    if [ "$http_code" = "200" ]; then
        echo -n "."
        return 0
    else
        echo -n "x"
        return 1
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE RUNNER - Runs one phase for one king
# ═══════════════════════════════════════════════════════════════════════════════

run_king_phase() {
    local king=$1
    local url=$2
    local model=$3
    local duration=$4
    local phase=$5
    local interval=$6
    local timeout=$7
    
    local output_dir="$RESULTS_DIR/$king/$phase"
    
    # Select prompts based on phase
    if [ "$phase" = "basic" ]; then
        local prompts=("${BASIC_PROMPTS[@]}")
    else
        local prompts=("${COMPLEX_PROMPTS[@]}")
    fi
    local num_prompts=${#prompts[@]}
    
    log "[$king] Starting $phase phase"
    log "[$king]   Duration: ${duration}s | Interval: ${interval}s | Timeout: ${timeout}s"
    log "[$king]   Expected requests: ~$((duration / interval))"
    
    local start_time=$(date +%s)
    local end_time=$((start_time + duration))
    local request_num=0
    local success_count=0
    local fail_count=0
    
    echo -n "[$king $phase] "
    
    while [ $(date +%s) -lt $end_time ]; do
        request_num=$((request_num + 1))
        
        # Cycle through prompts
        local prompt_idx=$(( (request_num - 1) % num_prompts ))
        local prompt="${prompts[$prompt_idx]}"
        
        if send_request "$king" "$url" "$model" "$prompt" "$phase" "$request_num" "$timeout" "$output_dir"; then
            success_count=$((success_count + 1))
        else
            fail_count=$((fail_count + 1))
        fi
        
        # Progress report every 30 requests
        if [ $((request_num % 30)) -eq 0 ]; then
            local current_time=$(date +%s)
            local remaining=$((end_time - current_time))
            local rate=$(echo "scale=2; $request_num / ($current_time - $start_time) * 60" | bc 2>/dev/null || echo "?")
            echo ""
            log "[$king $phase] Progress: $request_num requests | $success_count ok | $fail_count fail | ${remaining}s remaining | ~${rate} req/min"
            echo -n "[$king $phase] "
        fi
        
        sleep "$interval"
    done
    
    echo ""
    local actual_duration=$(($(date +%s) - start_time))
    log "[$king] $phase COMPLETE: $request_num requests ($success_count success, $fail_count fail) in ${actual_duration}s"
    
    # Save phase statistics
    cat > "$RESULTS_DIR/stats/${king}_${phase}_stats.json" << STATSEOF
{
    "king": "$king",
    "model": "$model",
    "phase": "$phase",
    "total_requests": $request_num,
    "successful": $success_count,
    "failed": $fail_count,
    "success_rate": $(echo "scale=4; $success_count / $request_num * 100" | bc 2>/dev/null || echo "0"),
    "planned_duration_seconds": $duration,
    "actual_duration_seconds": $actual_duration,
    "interval_seconds": $interval,
    "timeout_seconds": $timeout,
    "started_at": "$(date -d @$start_time -Iseconds 2>/dev/null || date -r $start_time -Iseconds)",
    "completed_at": "$(date -Iseconds)"
}
STATSEOF
}

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN EXECUTION
# ═══════════════════════════════════════════════════════════════════════════════

echo ""
echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║                                                                              ║"
echo "║            ⚔️   OVERNIGHT STRESS TEST - WAR OF THREE KINGS   ⚔️              ║"
echo "║                                                                              ║"
echo "║     Total Duration: 5 hours                                                  ║"
echo "║     Phase 1 (BASIC):   2.5 hours @ 1 request every ${BASIC_INTERVAL}s per king              ║"
echo "║     Phase 2 (COMPLEX): 2.5 hours @ 1 request every ${COMPLEX_INTERVAL}s per king             ║"
echo "║                                                                              ║"
echo "║     Expected Requests:                                                       ║"
echo "║       BASIC:   ~900/king × 3 kings = ~2,700 total                           ║"
echo "║       COMPLEX: ~200/king × 3 kings = ~600 total                             ║"
echo "║       TOTAL:   ~3,300 requests over 5 hours                                 ║"
echo "║                                                                              ║"
echo "║     👑 Qwen Emperor    🦙 Llama Lord    🔮 Mixtral Maven                    ║"
echo "║                                                                              ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
echo ""

# Setup
setup_directories

# Save test configuration
cat > "$RESULTS_DIR/config.json" << CONFIGEOF
{
    "test_name": "Overnight Stress Test - War of Three Kings",
    "version": "1.0",
    "started_at": "$(date -Iseconds)",
    "configuration": {
        "phase1_duration_seconds": $PHASE1_DURATION,
        "phase2_duration_seconds": $PHASE2_DURATION,
        "basic_interval_seconds": $BASIC_INTERVAL,
        "complex_interval_seconds": $COMPLEX_INTERVAL,
        "basic_timeout_seconds": $BASIC_TIMEOUT,
        "complex_timeout_seconds": $COMPLEX_TIMEOUT
    },
    "kings": {
        "qwen": {
            "url": "$QWEN_URL",
            "model": "$QWEN_MODEL"
        },
        "llama": {
            "url": "$LLAMA_URL",
            "model": "$LLAMA_MODEL"
        },
        "mixtral": {
            "url": "$MIXTRAL_URL",
            "model": "$MIXTRAL_MODEL"
        }
    },
    "prompts": {
        "basic_count": ${#BASIC_PROMPTS[@]},
        "complex_count": ${#COMPLEX_PROMPTS[@]}
    }
}
CONFIGEOF

log "Configuration saved to $RESULTS_DIR/config.json"

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 1: BASIC QUESTIONS
# ═══════════════════════════════════════════════════════════════════════════════

echo ""
log "═══════════════════════════════════════════════════════════════════════════"
log "PHASE 1: BASIC QUESTIONS (2.5 hours)"
log "  High frequency simple prompts to test throughput and stability"
log "═══════════════════════════════════════════════════════════════════════════"
echo ""

# Run all three kings in PARALLEL
run_king_phase "qwen" "$QWEN_URL" "$QWEN_MODEL" "$PHASE1_DURATION" "basic" "$BASIC_INTERVAL" "$BASIC_TIMEOUT" &
QWEN_PID=$!

run_king_phase "llama" "$LLAMA_URL" "$LLAMA_MODEL" "$PHASE1_DURATION" "basic" "$BASIC_INTERVAL" "$BASIC_TIMEOUT" &
LLAMA_PID=$!

run_king_phase "mixtral" "$MIXTRAL_URL" "$MIXTRAL_MODEL" "$PHASE1_DURATION" "basic" "$BASIC_INTERVAL" "$BASIC_TIMEOUT" &
MIXTRAL_PID=$!

# Wait for all basic phases to complete
log "Waiting for all BASIC phases to complete..."
wait $QWEN_PID $LLAMA_PID $MIXTRAL_PID

echo ""
log "═══════════════════════════════════════════════════════════════════════════"
log "PHASE 1 COMPLETE"
log "  Cooling down for 30 seconds before Phase 2..."
log "═══════════════════════════════════════════════════════════════════════════"
sleep 30

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 2: COMPLEX QUESTIONS
# ═══════════════════════════════════════════════════════════════════════════════

echo ""
log "═══════════════════════════════════════════════════════════════════════════"
log "PHASE 2: COMPLEX QUESTIONS (2.5 hours)"
log "  Lower frequency reasoning challenges to test intelligence under load"
log "═══════════════════════════════════════════════════════════════════════════"
echo ""

# Run all three kings in PARALLEL
run_king_phase "qwen" "$QWEN_URL" "$QWEN_MODEL" "$PHASE2_DURATION" "complex" "$COMPLEX_INTERVAL" "$COMPLEX_TIMEOUT" &
QWEN_PID=$!

run_king_phase "llama" "$LLAMA_URL" "$LLAMA_MODEL" "$PHASE2_DURATION" "complex" "$COMPLEX_INTERVAL" "$COMPLEX_TIMEOUT" &
LLAMA_PID=$!

run_king_phase "mixtral" "$MIXTRAL_URL" "$MIXTRAL_MODEL" "$PHASE2_DURATION" "complex" "$COMPLEX_INTERVAL" "$COMPLEX_TIMEOUT" &
MIXTRAL_PID=$!

# Wait for all complex phases to complete
log "Waiting for all COMPLEX phases to complete..."
wait $QWEN_PID $LLAMA_PID $MIXTRAL_PID

# ═══════════════════════════════════════════════════════════════════════════════
# FINAL SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════

echo ""
log "═══════════════════════════════════════════════════════════════════════════"
log "OVERNIGHT STRESS TEST COMPLETE!"
log "═══════════════════════════════════════════════════════════════════════════"

# Count files
QWEN_BASIC=$(ls -1 "$RESULTS_DIR/qwen/basic/"*.json 2>/dev/null | wc -l | tr -d ' ')
QWEN_COMPLEX=$(ls -1 "$RESULTS_DIR/qwen/complex/"*.json 2>/dev/null | wc -l | tr -d ' ')
LLAMA_BASIC=$(ls -1 "$RESULTS_DIR/llama/basic/"*.json 2>/dev/null | wc -l | tr -d ' ')
LLAMA_COMPLEX=$(ls -1 "$RESULTS_DIR/llama/complex/"*.json 2>/dev/null | wc -l | tr -d ' ')
MIXTRAL_BASIC=$(ls -1 "$RESULTS_DIR/mixtral/basic/"*.json 2>/dev/null | wc -l | tr -d ' ')
MIXTRAL_COMPLEX=$(ls -1 "$RESULTS_DIR/mixtral/complex/"*.json 2>/dev/null | wc -l | tr -d ' ')
TOTAL=$((QWEN_BASIC + QWEN_COMPLEX + LLAMA_BASIC + LLAMA_COMPLEX + MIXTRAL_BASIC + MIXTRAL_COMPLEX))

# Generate final summary
cat > "$RESULTS_DIR/FINAL_SUMMARY.json" << SUMMARYEOF
{
    "test_name": "Overnight Stress Test - War of Three Kings",
    "completed_at": "$(date -Iseconds)",
    "results_directory": "$RESULTS_DIR",
    "total_responses_captured": $TOTAL,
    "file_counts": {
        "qwen": {
            "basic": $QWEN_BASIC,
            "complex": $QWEN_COMPLEX,
            "total": $((QWEN_BASIC + QWEN_COMPLEX))
        },
        "llama": {
            "basic": $LLAMA_BASIC,
            "complex": $LLAMA_COMPLEX,
            "total": $((LLAMA_BASIC + LLAMA_COMPLEX))
        },
        "mixtral": {
            "basic": $MIXTRAL_BASIC,
            "complex": $MIXTRAL_COMPLEX,
            "total": $((MIXTRAL_BASIC + MIXTRAL_COMPLEX))
        }
    }
}
SUMMARYEOF

echo ""
log "RESULTS SUMMARY"
log "───────────────────────────────────────────────────────────────────"
echo ""
echo "  👑 Qwen Emperor:   $QWEN_BASIC basic + $QWEN_COMPLEX complex = $((QWEN_BASIC + QWEN_COMPLEX)) responses"
echo "  🦙 Llama Lord:     $LLAMA_BASIC basic + $LLAMA_COMPLEX complex = $((LLAMA_BASIC + LLAMA_COMPLEX)) responses"
echo "  🔮 Mixtral Maven:  $MIXTRAL_BASIC basic + $MIXTRAL_COMPLEX complex = $((MIXTRAL_BASIC + MIXTRAL_COMPLEX)) responses"
echo ""
echo "  📊 TOTAL CAPTURED: $TOTAL responses"
echo ""
log "───────────────────────────────────────────────────────────────────"
log "Results saved to: $RESULTS_DIR"
log "Ready for Claude analysis!"
log "───────────────────────────────────────────────────────────────────"

echo ""
echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║                                                                              ║"
echo "║                      🏆 TEST COMPLETE - SLEEP WELL! 🏆                       ║"
echo "║                                                                              ║"
echo "║     All $TOTAL responses have been captured and saved.                    ║"
echo "║     Review with: ls -la $RESULTS_DIR/                     ║"
echo "║                                                                              ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
echo ""
