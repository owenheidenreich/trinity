#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# ⚔️  WAR OF THREE KINGS - QUICK BATTLE (Engineering Grade) ⚔️
# ═══════════════════════════════════════════════════════════════════════════════
#
# 30-MINUTE FOCUSED BENCHMARK
# - Phase 1: Health Check & Warm-up (2 min)
# - Phase 2: IQ Battle - 25 scored questions (10 min)
# - Phase 3: Speed Trial - Throughput test (8 min)
# - Phase 4: Reasoning Gauntlet - 10 hard problems (10 min)
#
# Total: ~30 minutes, ~150 meaningful data points per king
#
# Usage:
#   ./quick-battle.sh              # Run full battle
#   ./quick-battle.sh --king qwen  # Test single king
#   ./quick-battle.sh --phase 2    # Run single phase
#
# ═══════════════════════════════════════════════════════════════════════════════

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_BASE="$SCRIPT_DIR/../results/battles"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RESULTS_DIR="$RESULTS_BASE/battle_$TIMESTAMP"

# ═══════════════════════════════════════════════════════════════════════════════
# KING REGISTRY - Update these when deployments change
# ═══════════════════════════════════════════════════════════════════════════════

declare -A KINGS=(
    ["qwen"]="https://sptj5nup2lc939i2h4bhq532gs.ingress.quanglong.org|qwen2.5:72b|👑"
    ["llama"]="http://56oqg7o6n9fu53ijan3udmmb5o.ingress.h4i-dedicated.eu-sw-2.digitalfrontier.so|llama3.3:70b|🦙"
    ["mixtral"]="https://bnivii01v9bcbchrqtej5pmd0k.ingress.4090.akashgpu.com|mixtral:8x22b|🔮"
)

# Parse king config
get_king_url() { echo "${KINGS[$1]}" | cut -d'|' -f1; }
get_king_model() { echo "${KINGS[$1]}" | cut -d'|' -f2; }
get_king_icon() { echo "${KINGS[$1]}" | cut -d'|' -f3; }

# Active kings (will be populated by health check)
ACTIVE_KINGS=()

# ═══════════════════════════════════════════════════════════════════════════════
# IQ TEST QUESTIONS - Scored, with expected answers
# ═══════════════════════════════════════════════════════════════════════════════

# Format: "question|expected_answer|category|difficulty"
IQ_QUESTIONS=(
    # MATH (5 questions)
    "What is 17 × 24?|408|math|easy"
    "What is the square root of 144?|12|math|easy"
    "If x + 5 = 12, what is x?|7|math|easy"
    "What is 15% of 80?|12|math|medium"
    "A train travels 120 miles in 2 hours. What is its speed in mph?|60|math|medium"
    
    # LOGIC (5 questions)
    "All roses are flowers. Some flowers fade quickly. Can we conclude all roses fade quickly?|no|logic|medium"
    "If it rains, the ground is wet. The ground is wet. Did it rain?|not necessarily|logic|medium"
    "A bat and ball cost $1.10. The bat costs $1 more than the ball. How much is the ball?|0.05|logic|hard"
    "Sally has 3 brothers. Each brother has 2 sisters. How many sisters does Sally have?|1|logic|hard"
    "How many times does 'r' appear in 'strawberry'?|3|logic|hard"
    
    # KNOWLEDGE (5 questions)
    "What is the capital of Australia?|Canberra|knowledge|easy"
    "Who wrote 'Romeo and Juliet'?|Shakespeare|knowledge|easy"
    "What is the chemical symbol for gold?|Au|knowledge|easy"
    "In what year did World War II end?|1945|knowledge|medium"
    "What is the largest planet in our solar system?|Jupiter|knowledge|easy"
    
    # CODING (5 questions)
    "In Python, what does len([1,2,3]) return?|3|coding|easy"
    "What is the time complexity of binary search?|O(log n)|coding|medium"
    "In JavaScript, what does typeof null return?|object|coding|medium"
    "What data structure uses LIFO?|stack|coding|easy"
    "What does SQL stand for?|Structured Query Language|coding|easy"
    
    # REASONING (5 questions)
    "If 5 machines take 5 minutes to make 5 widgets, how long for 100 machines to make 100 widgets?|5|reasoning|hard"
    "I have two coins totaling 30 cents. One is not a nickel. What are they?|quarter and nickel|reasoning|hard"
    "A farmer has 17 sheep. All but 9 die. How many are left?|9|reasoning|medium"
    "What comes next: 2, 6, 12, 20, 30, ?|42|reasoning|medium"
    "If you rearrange 'CIFAIPC', you get the name of a?|ocean (PACIFIC)|reasoning|medium"
)

# ═══════════════════════════════════════════════════════════════════════════════
# REASONING GAUNTLET - Complex problems requiring multi-step thinking
# ═══════════════════════════════════════════════════════════════════════════════

GAUNTLET_PROBLEMS=(
    "Write a Python function that checks if a string is a valid palindrome, ignoring spaces and punctuation. Include a brief explanation."
    "Explain the difference between TCP and UDP in exactly 3 sentences."
    "A clock shows 3:15. What is the angle between the hour and minute hands? Show your calculation."
    "Write a SQL query to find the second highest salary from an employees table. Explain why your approach works."
    "You have 8 balls, one is heavier. You have a balance scale and can use it twice. How do you find the heavy ball?"
    "Implement a function to reverse a linked list in Python. Include time and space complexity."
    "Explain the CAP theorem in distributed systems. Give one real-world example."
    "What is the output of: print([x*2 for x in range(5) if x%2==0]) in Python?"
    "A lily pad doubles in size every day. If it takes 48 days to cover a lake, how many days to cover half?|47"
    "Write a regex pattern that matches valid email addresses. Explain each part."
)

# ═══════════════════════════════════════════════════════════════════════════════
# SPEED TRIAL PROMPTS - Short, consistent for throughput testing
# ═══════════════════════════════════════════════════════════════════════════════

SPEED_PROMPTS=(
    "Say 'hello' and nothing else."
    "What is 1+1?"
    "Name one color."
    "Yes or no: Is water wet?"
    "Count to 3."
)

# ═══════════════════════════════════════════════════════════════════════════════
# UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

log() { echo "[$(date '+%H:%M:%S')] $1"; }
log_phase() { echo ""; echo "═══════════════════════════════════════════════════════════════"; log "$1"; echo "═══════════════════════════════════════════════════════════════"; }

setup_directories() {
    mkdir -p "$RESULTS_DIR"/{health,iq,speed,gauntlet,summary}
    for king in "${!KINGS[@]}"; do
        mkdir -p "$RESULTS_DIR"/{iq,speed,gauntlet}/"$king"
    done
    log "Results directory: $RESULTS_DIR"
}

# ═══════════════════════════════════════════════════════════════════════════════
# CORE: Send request and capture response
# ═══════════════════════════════════════════════════════════════════════════════

send_request() {
    local king=$1
    local prompt=$2
    local timeout=${3:-60}
    local max_tokens=${4:-500}
    
    local url=$(get_king_url "$king")
    local model=$(get_king_model "$king")
    
    local start_time=$(date +%s.%N)
    
    local escaped_prompt=$(printf '%s' "$prompt" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')
    
    local response=$(curl -s --max-time "$timeout" \
        -X POST "$url/api/generate" \
        -H "Content-Type: application/json" \
        -d "{
            \"model\": \"$model\",
            \"prompt\": $escaped_prompt,
            \"stream\": false,
            \"options\": {\"num_predict\": $max_tokens, \"temperature\": 0.1}
        }" 2>/dev/null)
    
    local end_time=$(date +%s.%N)
    local elapsed=$(echo "$end_time - $start_time" | bc 2>/dev/null || echo "0")
    
    # Extract response text
    local answer=$(echo "$response" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('response',''))" 2>/dev/null || echo "")
    local tokens=$(echo "$response" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('eval_count',0))" 2>/dev/null || echo "0")
    
    # Return JSON
    echo "{\"king\":\"$king\",\"elapsed\":$elapsed,\"tokens\":$tokens,\"response\":$(echo "$answer" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))' 2>/dev/null || echo '""')}"
}

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 1: HEALTH CHECK & WARM-UP
# ═══════════════════════════════════════════════════════════════════════════════

phase_health() {
    log_phase "PHASE 1: HEALTH CHECK & WARM-UP"
    
    for king in "${!KINGS[@]}"; do
        local icon=$(get_king_icon "$king")
        local url=$(get_king_url "$king")
        
        echo -n "  $icon $king: "
        
        # Quick health check
        local health=$(curl -s --max-time 10 "$url/api/tags" 2>/dev/null)
        
        if echo "$health" | grep -q "models"; then
            echo -n "✓ online, warming up... "
            
            # Warm-up request
            local warmup=$(send_request "$king" "Say hello." 30 50)
            local elapsed=$(echo "$warmup" | python3 -c "import json,sys; print(json.load(sys.stdin).get('elapsed',0))" 2>/dev/null)
            
            if [ -n "$elapsed" ] && [ "$elapsed" != "0" ]; then
                echo "✓ ready (${elapsed}s)"
                ACTIVE_KINGS+=("$king")
                echo "$warmup" > "$RESULTS_DIR/health/${king}_warmup.json"
            else
                echo "✗ warm-up failed"
            fi
        else
            echo "✗ offline (502)"
        fi
    done
    
    echo ""
    log "Active kings: ${ACTIVE_KINGS[*]:-NONE}"
    
    if [ ${#ACTIVE_KINGS[@]} -eq 0 ]; then
        log "ERROR: No kings available. Exiting."
        exit 1
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 2: IQ BATTLE - Scored questions
# ═══════════════════════════════════════════════════════════════════════════════

phase_iq() {
    log_phase "PHASE 2: IQ BATTLE (25 scored questions)"
    
    local total_questions=${#IQ_QUESTIONS[@]}
    
    for king in "${ACTIVE_KINGS[@]}"; do
        local icon=$(get_king_icon "$king")
        local score=0
        local times=()
        
        log "$icon $king - Starting IQ test"
        
        for i in "${!IQ_QUESTIONS[@]}"; do
            local qdata="${IQ_QUESTIONS[$i]}"
            local question=$(echo "$qdata" | cut -d'|' -f1)
            local expected=$(echo "$qdata" | cut -d'|' -f2)
            local category=$(echo "$qdata" | cut -d'|' -f3)
            local difficulty=$(echo "$qdata" | cut -d'|' -f4)
            
            local result=$(send_request "$king" "$question Answer concisely in 1-2 words if possible." 30 100)
            local response=$(echo "$result" | python3 -c "import json,sys; print(json.load(sys.stdin).get('response','').lower())" 2>/dev/null)
            local elapsed=$(echo "$result" | python3 -c "import json,sys; print(json.load(sys.stdin).get('elapsed',0))" 2>/dev/null)
            
            # Simple scoring: check if expected answer appears in response
            local correct=0
            if echo "$response" | grep -qi "$expected"; then
                correct=1
                score=$((score + 1))
                echo -n "✓"
            else
                echo -n "✗"
            fi
            
            times+=("$elapsed")
            
            # Save detailed result
            cat > "$RESULTS_DIR/iq/$king/q${i}.json" << EOF
{
    "question_num": $i,
    "question": $(echo "$question" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))'),
    "expected": "$expected",
    "category": "$category",
    "difficulty": "$difficulty",
    "response": $(echo "$response" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))'),
    "correct": $correct,
    "elapsed": $elapsed
}
EOF
        done
        
        local avg_time=$(echo "${times[@]}" | tr ' ' '\n' | awk '{s+=$1}END{print s/NR}')
        echo ""
        log "$icon $king: Score $score/$total_questions (${avg_time}s avg)"
        
        # Save king summary
        echo "{\"king\":\"$king\",\"score\":$score,\"total\":$total_questions,\"avg_time\":$avg_time}" > "$RESULTS_DIR/iq/${king}_summary.json"
    done
}

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 3: SPEED TRIAL - Throughput test
# ═══════════════════════════════════════════════════════════════════════════════

phase_speed() {
    log_phase "PHASE 3: SPEED TRIAL (Throughput Test)"
    
    local requests_per_test=20
    
    for king in "${ACTIVE_KINGS[@]}"; do
        local icon=$(get_king_icon "$king")
        local times=()
        local tokens_total=0
        
        log "$icon $king - Sending $requests_per_test rapid requests"
        echo -n "  "
        
        for i in $(seq 1 $requests_per_test); do
            local prompt="${SPEED_PROMPTS[$((i % ${#SPEED_PROMPTS[@]}))]}"
            local result=$(send_request "$king" "$prompt" 15 20)
            local elapsed=$(echo "$result" | python3 -c "import json,sys; print(json.load(sys.stdin).get('elapsed',0))" 2>/dev/null)
            local tokens=$(echo "$result" | python3 -c "import json,sys; print(json.load(sys.stdin).get('tokens',0))" 2>/dev/null)
            
            if [ "$elapsed" != "0" ] && [ -n "$elapsed" ]; then
                echo -n "."
                times+=("$elapsed")
                tokens_total=$((tokens_total + tokens))
            else
                echo -n "x"
            fi
            
            echo "$result" > "$RESULTS_DIR/speed/$king/req${i}.json"
        done
        
        echo ""
        
        local success=${#times[@]}
        local avg_time=$(echo "${times[@]}" | tr ' ' '\n' | awk '{s+=$1}END{if(NR>0)print s/NR; else print 0}')
        local min_time=$(echo "${times[@]}" | tr ' ' '\n' | sort -n | head -1)
        local max_time=$(echo "${times[@]}" | tr ' ' '\n' | sort -n | tail -1)
        local total_time=$(echo "${times[@]}" | tr ' ' '\n' | awk '{s+=$1}END{print s}')
        local rps=$(echo "scale=2; $success / $total_time" | bc 2>/dev/null || echo "0")
        
        log "$icon $king: $success/$requests_per_test success | ${avg_time}s avg | ${rps} req/s"
        
        cat > "$RESULTS_DIR/speed/${king}_summary.json" << EOF
{
    "king": "$king",
    "requests": $requests_per_test,
    "successful": $success,
    "avg_latency": $avg_time,
    "min_latency": ${min_time:-0},
    "max_latency": ${max_time:-0},
    "requests_per_second": $rps,
    "total_tokens": $tokens_total
}
EOF
    done
}

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 4: REASONING GAUNTLET - Complex problems
# ═══════════════════════════════════════════════════════════════════════════════

phase_gauntlet() {
    log_phase "PHASE 4: REASONING GAUNTLET (10 hard problems)"
    
    for king in "${ACTIVE_KINGS[@]}"; do
        local icon=$(get_king_icon "$king")
        local times=()
        local tokens_total=0
        
        log "$icon $king - Starting gauntlet"
        
        for i in "${!GAUNTLET_PROBLEMS[@]}"; do
            local problem="${GAUNTLET_PROBLEMS[$i]}"
            echo -n "  Problem $((i+1))/10: "
            
            local result=$(send_request "$king" "$problem" 120 1000)
            local elapsed=$(echo "$result" | python3 -c "import json,sys; print(json.load(sys.stdin).get('elapsed',0))" 2>/dev/null)
            local tokens=$(echo "$result" | python3 -c "import json,sys; print(json.load(sys.stdin).get('tokens',0))" 2>/dev/null)
            local response=$(echo "$result" | python3 -c "import json,sys; print(json.load(sys.stdin).get('response','')[:100])" 2>/dev/null)
            
            if [ "$elapsed" != "0" ] && [ -n "$elapsed" ]; then
                echo "${elapsed}s (${tokens} tokens)"
                times+=("$elapsed")
                tokens_total=$((tokens_total + tokens))
            else
                echo "FAILED"
            fi
            
            echo "$result" > "$RESULTS_DIR/gauntlet/$king/problem${i}.json"
        done
        
        local avg_time=$(echo "${times[@]}" | tr ' ' '\n' | awk '{s+=$1}END{if(NR>0)print s/NR; else print 0}')
        log "$icon $king: Completed ${#times[@]}/10 | ${avg_time}s avg | $tokens_total total tokens"
        
        cat > "$RESULTS_DIR/gauntlet/${king}_summary.json" << EOF
{
    "king": "$king",
    "completed": ${#times[@]},
    "total": 10,
    "avg_time": $avg_time,
    "total_tokens": $tokens_total
}
EOF
    done
}

# ═══════════════════════════════════════════════════════════════════════════════
# FINAL: Generate battle report
# ═══════════════════════════════════════════════════════════════════════════════

generate_report() {
    log_phase "BATTLE COMPLETE - GENERATING REPORT"
    
    local report="$RESULTS_DIR/BATTLE_REPORT.md"
    
    cat > "$report" << 'HEADER'
# ⚔️ War of Three Kings - Battle Report

Generated: TIMESTAMP

## Summary

HEADER
    
    sed -i '' "s/TIMESTAMP/$(date -Iseconds)/" "$report" 2>/dev/null || sed -i "s/TIMESTAMP/$(date -Iseconds)/" "$report"
    
    echo "| King | IQ Score | Avg Latency | Speed (req/s) | Gauntlet |" >> "$report"
    echo "|------|----------|-------------|---------------|----------|" >> "$report"
    
    for king in "${ACTIVE_KINGS[@]}"; do
        local icon=$(get_king_icon "$king")
        local iq_score=$(cat "$RESULTS_DIR/iq/${king}_summary.json" 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print(f\"{d['score']}/{d['total']}\")" 2>/dev/null || echo "N/A")
        local speed_data=$(cat "$RESULTS_DIR/speed/${king}_summary.json" 2>/dev/null)
        local avg_latency=$(echo "$speed_data" | python3 -c "import json,sys; print(f\"{json.load(sys.stdin)['avg_latency']:.2f}s\")" 2>/dev/null || echo "N/A")
        local rps=$(echo "$speed_data" | python3 -c "import json,sys; print(f\"{json.load(sys.stdin)['requests_per_second']}\")" 2>/dev/null || echo "N/A")
        local gauntlet=$(cat "$RESULTS_DIR/gauntlet/${king}_summary.json" 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print(f\"{d['completed']}/10\")" 2>/dev/null || echo "N/A")
        
        echo "| $icon $king | $iq_score | $avg_latency | $rps | $gauntlet |" >> "$report"
    done
    
    echo "" >> "$report"
    echo "## Detailed Results" >> "$report"
    echo "" >> "$report"
    echo "See individual JSON files in: \`$RESULTS_DIR\`" >> "$report"
    
    log "Report saved: $report"
    cat "$report"
}

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

main() {
    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║     ⚔️  WAR OF THREE KINGS - QUICK BATTLE  ⚔️                ║"
    echo "║                                                              ║"
    echo "║     Duration: ~30 minutes                                    ║"
    echo "║     Phases: Health → IQ → Speed → Gauntlet                   ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""
    
    setup_directories
    
    local start_time=$(date +%s)
    
    phase_health
    
    if [ ${#ACTIVE_KINGS[@]} -gt 0 ]; then
        phase_iq
        phase_speed
        phase_gauntlet
        generate_report
    fi
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    echo ""
    log "═══════════════════════════════════════════════════════════════"
    log "BATTLE COMPLETE in ${duration} seconds"
    log "Results: $RESULTS_DIR"
    log "═══════════════════════════════════════════════════════════════"
}

main "$@"
