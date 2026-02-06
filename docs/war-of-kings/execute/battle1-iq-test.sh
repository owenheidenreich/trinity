#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# ⚔️  WAR OF THREE KINGS - BATTLE 1: THE IQ TEST ⚔️
# ═══════════════════════════════════════════════════════════════════════════════
#
# 25 progressively harder questions to measure raw intelligence
# Run this script with: ./battle1-iq-test.sh [qwen|llama|mixtral|all]
#
# Output: JSON files with full responses, timing, and errors
# ═══════════════════════════════════════════════════════════════════════════════

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="$SCRIPT_DIR/../results/raw"
TIMEOUT=90

# King endpoints
QWEN_URL="https://sptj5nup2lc939i2h4bhq532gs.ingress.quanglong.org"
LLAMA_URL="http://56oqg7o6n9fu53ijan3udmmb5o.ingress.h4i-dedicated.eu-sw-2.digitalfrontier.so"
MIXTRAL_URL="https://bnivii01v9bcbchrqtej5pmd0k.ingress.4090.akashgpu.com"

# Models
QWEN_MODEL="qwen2.5:72b"
LLAMA_MODEL="llama3.3:70b"
MIXTRAL_MODEL="mixtral:8x22b"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# ═══════════════════════════════════════════════════════════════════════════════
# IQ TEST QUESTIONS (25 total, 5 categories)
# ═══════════════════════════════════════════════════════════════════════════════

declare -a QUESTIONS=(
    # Category 1: Arithmetic (Q1-Q3)
    "Q01|ARITHMETIC|What is the square root of 144? Answer with just the number.|12"
    "Q02|ARITHMETIC|What is 15% of 80? Answer with just the number.|12"
    "Q03|ARITHMETIC|What is 2 to the power of 10? Answer with just the number.|1024"
    
    # Category 2: Word Problem Traps (Q4-Q6)
    "Q04|WORD_TRAP|I have 3 apples. I give away 2 oranges. How many apples do I have?|3"
    "Q05|WORD_TRAP|Which weighs more: a pound of steel or a pound of feathers?|same"
    "Q06|WORD_TRAP|A bat and a ball cost \$1.10 together. The bat costs \$1.00 more than the ball. How much does the ball cost? Show your work.|0.05"
    
    # Category 3: Logic Traps (Q7-Q10)
    "Q07|LOGIC|Sally has 3 brothers. Each brother has 2 sisters. How many sisters does Sally have?|1"
    "Q08|LOGIC|How many times does the letter 'r' appear in the word 'strawberry'? Count carefully.|3"
    "Q09|LOGIC|A farmer has 17 sheep. All but 9 run away. How many sheep does the farmer have left?|9"
    "Q10|LOGIC|Two trains are 100 miles apart, heading toward each other. Train A travels 40 mph, Train B travels 60 mph. How long until they meet? Answer in hours.|1"
    
    # Category 4: Formal Logic (Q11-Q13)
    "Q11|FORMAL_LOGIC|You meet three people: A, B, and C. A says 'I always lie.' B says 'A is telling the truth.' C says 'B always lies.' Who is definitely a liar?|A"
    "Q12|FORMAL_LOGIC|On an island, knights always tell truth, knaves always lie. You meet someone who says 'I am a knave.' What are they?|paradox"
    "Q13|FORMAL_LOGIC|In the Monty Hall problem, you pick door 1. The host opens door 3 revealing a goat. Should you switch to door 2? Explain with probability.|switch"
    
    # Category 5: Mathematical Proofs (Q14-Q16)
    "Q14|MATH_PROOF|Prove that the sum of the first n odd numbers equals n². Use mathematical induction.|induction"
    "Q15|MATH_PROOF|Prove that the square root of 2 is irrational using proof by contradiction.|contradiction"
    "Q16|MATH_PROOF|Using the pigeonhole principle, prove that in any group of 13 people, at least 2 share a birthday month.|pigeonhole"
    
    # Category 6: Code (Q17-Q20)
    "Q17|CODE|Write a Python function that determines if a given number is a Carmichael number. Include the mathematical definition.|def"
    "Q18|CODE|Write a Python function for binary search that returns the index of the FIRST occurrence of the target. Handle duplicates.|def"
    "Q19|CODE|Write a Python class implementing an LRU cache with O(1) get and put operations. Use OrderedDict or your own implementation.|class"
    "Q20|CODE|What is the time complexity of quicksort in best, average, and worst cases? Explain why the worst case occurs.|O(n"
    
    # Category 7: Theory (Q21-Q23)
    "Q21|THEORY|Explain Gödel's First Incompleteness Theorem in simple terms. What does it mean for mathematics?|unprovable"
    "Q22|THEORY|Explain the P vs NP problem. Give an example of an NP-complete problem.|NP"
    "Q23|THEORY|Explain why the halting problem is undecidable. Sketch the proof.|undecidable"
    
    # Category 8: Systems (Q24-Q25)
    "Q24|SYSTEMS|Explain the CAP theorem. Give an example of a CP system and an AP system.|CAP"
    "Q25|SYSTEMS|Explain the difference between strong consistency and eventual consistency. When would you choose each?|consistency"
)

# ═══════════════════════════════════════════════════════════════════════════════
# FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

run_question() {
    local king_name=$1
    local king_url=$2
    local king_model=$3
    local question_id=$4
    local category=$5
    local prompt=$6
    local expected=$7
    local output_dir=$8
    
    local output_file="$output_dir/${question_id}.json"
    local timestamp=$(date +%Y%m%d_%H%M%S)
    
    echo -n "  [$question_id] $category: "
    
    # Build the request with timing
    local start_time=$(date +%s.%N)
    
    # Make request and capture everything
    local response
    local http_code
    local curl_exit
    
    response=$(curl -s -w "\n%{http_code}" --max-time $TIMEOUT \
        -X POST "$king_url/generate" \
        -H "Content-Type: application/json" \
        -d "{
            \"model\": \"$king_model\",
            \"prompt\": \"$prompt\",
            \"stream\": false,
            \"options\": {
                \"num_predict\": 2000,
                \"temperature\": 0.1
            }
        }" 2>&1) || curl_exit=$?
    
    local end_time=$(date +%s.%N)
    local elapsed=$(echo "$end_time - $start_time" | bc)
    
    # Parse response
    http_code=$(echo "$response" | tail -n1)
    local body=$(echo "$response" | sed '$d')
    
    # Extract answer from JSON response
    local answer=$(echo "$body" | grep -o '"response":"[^"]*"' | sed 's/"response":"//;s/"$//' | head -c 2000 2>/dev/null || echo "")
    
    # Check for expected keyword
    local correct="false"
    if echo "$answer" | grep -qi "$expected"; then
        correct="true"
        echo -e "${GREEN}✓${NC} (${elapsed}s)"
    else
        echo -e "${RED}✗${NC} (${elapsed}s)"
    fi
    
    # Write full output to JSON file
    cat > "$output_file" << EOF
{
    "king": "$king_name",
    "question_id": "$question_id",
    "category": "$category",
    "prompt": $(echo "$prompt" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))'),
    "expected_keyword": "$expected",
    "timestamp": "$timestamp",
    "timing": {
        "start": "$start_time",
        "end": "$end_time",
        "elapsed_seconds": $elapsed
    },
    "http_code": "$http_code",
    "curl_exit_code": "${curl_exit:-0}",
    "correct": $correct,
    "raw_response": $body,
    "extracted_answer": $(echo "$answer" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))' 2>/dev/null || echo '""')
}
EOF
}

run_battle_for_king() {
    local king_name=$1
    local king_url=$2
    local king_model=$3
    local emoji=$4
    
    local output_dir="$RESULTS_DIR/$king_name/battle1-iq"
    mkdir -p "$output_dir"
    
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo "$emoji BATTLE 1: IQ TEST - $king_name"
    echo "═══════════════════════════════════════════════════════════════"
    echo "URL: $king_url"
    echo "Model: $king_model"
    echo "Output: $output_dir"
    echo "───────────────────────────────────────────────────────────────"
    
    local correct_count=0
    local total_count=0
    local start_battle=$(date +%s)
    
    for q in "${QUESTIONS[@]}"; do
        IFS='|' read -r qid category prompt expected <<< "$q"
        run_question "$king_name" "$king_url" "$king_model" "$qid" "$category" "$prompt" "$expected" "$output_dir"
        ((total_count++))
        
        # Count correct (check last file)
        if grep -q '"correct": true' "$output_dir/${qid}.json" 2>/dev/null; then
            ((correct_count++))
        fi
    done
    
    local end_battle=$(date +%s)
    local battle_time=$((end_battle - start_battle))
    
    echo "───────────────────────────────────────────────────────────────"
    echo "$emoji $king_name RESULTS: $correct_count / $total_count correct"
    echo "   Total time: ${battle_time}s"
    echo "═══════════════════════════════════════════════════════════════"
    
    # Write summary
    cat > "$output_dir/SUMMARY.json" << EOF
{
    "king": "$king_name",
    "battle": "IQ Test",
    "total_questions": $total_count,
    "correct_auto": $correct_count,
    "score_auto": $(echo "scale=2; $correct_count / $total_count * 100" | bc),
    "total_time_seconds": $battle_time,
    "timestamp": "$(date -Iseconds)"
}
EOF
}

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║        ⚔️  WAR OF THREE KINGS - BATTLE 1: IQ TEST ⚔️              ║"
echo "║                     $(date +%H:%M:%S)                                   ║"
echo "╚══════════════════════════════════════════════════════════════════╝"

case "${1:-all}" in
    qwen)
        run_battle_for_king "qwen" "$QWEN_URL" "$QWEN_MODEL" "👑"
        ;;
    llama)
        run_battle_for_king "llama" "$LLAMA_URL" "$LLAMA_MODEL" "🦙"
        ;;
    mixtral)
        run_battle_for_king "mixtral" "$MIXTRAL_URL" "$MIXTRAL_MODEL" "🔮"
        ;;
    all)
        run_battle_for_king "qwen" "$QWEN_URL" "$QWEN_MODEL" "👑"
        run_battle_for_king "llama" "$LLAMA_URL" "$LLAMA_MODEL" "🦙"
        run_battle_for_king "mixtral" "$MIXTRAL_URL" "$MIXTRAL_MODEL" "🔮"
        ;;
    *)
        echo "Usage: $0 [qwen|llama|mixtral|all]"
        exit 1
        ;;
esac

echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo "BATTLE 1 COMPLETE - Results saved to: $RESULTS_DIR/*/battle1-iq/"
echo "═══════════════════════════════════════════════════════════════════"
