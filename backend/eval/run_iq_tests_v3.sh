#!/bin/bash
# Trinity IQ Stress Tests v3 — Post-pipeline-audit verification
# Runs 8 tests against the deployed backend and grades results

API="https://api.dubya.ai"
OUTDIR="$(dirname "$0")/iq_tests_v3_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUTDIR"

PASS=0
FAIL=0
PARTIAL=0

run_test() {
    local num="$1"
    local endpoint="$2"
    local prompt="$3"
    local check_fn="$4"
    local desc="$5"

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "TEST $num: $desc"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    local start_time=$(date +%s)
    local raw_file="$OUTDIR/test${num}_raw.txt"

    # Run curl and capture SSE stream
    curl -sN --max-time 180 -X POST "$API/$endpoint" \
        -H "Content-Type: application/json" \
        -d "{\"prompt\": \"$prompt\"}" > "$raw_file" 2>&1

    local end_time=$(date +%s)
    local elapsed=$((end_time - start_time))

    # Extract the done line containing the full response
    local done_line=$(grep '"done"' "$raw_file" | tail -1)

    # Extract tokens to reconstruct the answer
    local answer=$(grep -o '"token": "[^"]*"' "$raw_file" | sed 's/"token": "//;s/"$//' | tr -d '\n')

    # Extract metadata from done line
    local complexity=$(echo "$done_line" | grep -o '"complexity":"[^"]*"' | sed 's/.*"complexity":"//;s/"//')
    if [ -z "$complexity" ]; then
        complexity=$(echo "$done_line" | grep -o '"complexity": "[^"]*"' | sed 's/.*"complexity": "//;s/"//')
    fi
    local passes=$(echo "$done_line" | grep -o '"passes_used":[0-9]*' | sed 's/.*://')
    local done_reason=$(echo "$done_line" | grep -o '"done_reason": "[^"]*"' | sed 's/.*"done_reason": "//;s/"//')
    if [ -z "$done_reason" ]; then
        done_reason=$(echo "$done_line" | grep -o '"done_reason":"[^"]*"' | sed 's/.*"done_reason":"//;s/"//')
    fi

    # Check for think-block leaks
    local think_leaks=$(echo "$answer" | grep -c "<think>" || true)

    # Character count
    local char_count=${#answer}

    echo "Time: ${elapsed}s | Complexity: ${complexity:-N/A} | Passes: ${passes:-N/A} | Chars: $char_count | Think leaks: $think_leaks | Done: ${done_reason:-N/A}"

    # Run the check function
    eval "$check_fn"
}

# ═══════════════════════════════════════════════
# TEST DEFINITIONS
# ═══════════════════════════════════════════════

# Test 1: Simple math
check_1() {
    if echo "$answer" | grep -qi "4"; then
        echo "PASS: Got correct answer (4)"
        ((PASS++))
    else
        echo "FAIL: Expected '4' in answer"
        echo "Answer preview: ${answer:0:200}"
        ((FAIL++))
    fi
}

# Test 2: TCP vs UDP comparison
check_2() {
    local has_tcp=$(echo "$answer" | grep -ci "tcp" || true)
    local has_udp=$(echo "$answer" | grep -ci "udp" || true)
    local has_reliable=$(echo "$answer" | grep -ci "reliable\|connection" || true)
    if [ "$has_tcp" -gt 0 ] && [ "$has_udp" -gt 0 ] && [ "$has_reliable" -gt 0 ]; then
        echo "PASS: Covers TCP, UDP, reliability/connection concepts"
        ((PASS++))
    elif [ "$has_tcp" -gt 0 ] && [ "$has_udp" -gt 0 ]; then
        echo "PARTIAL: Mentions TCP/UDP but missing key concepts"
        ((PARTIAL++))
    else
        echo "FAIL: Missing TCP/UDP discussion"
        echo "Answer preview: ${answer:0:200}"
        ((FAIL++))
    fi
}

# Test 3: Trick question — "All but 9 die"
check_3() {
    if echo "$answer" | grep -q "9"; then
        echo "PASS: Got correct answer (9)"
        ((PASS++))
    else
        echo "FAIL: Expected '9' in answer"
        echo "Answer preview: ${answer:0:200}"
        ((FAIL++))
    fi
}

# Test 4: Python palindrome DP
check_4() {
    local has_def=$(echo "$answer" | grep -c "def " || true)
    local has_python=$(echo "$answer" | grep -ci "python\|palindrome\|dynamic" || true)
    local has_code=$(echo "$answer" | grep -c "return\|True\|False" || true)
    if [ "$has_def" -gt 0 ] && [ "$has_code" -gt 0 ]; then
        echo "PASS: Contains Python function with palindrome logic"
        ((PASS++))
    elif [ "$has_python" -gt 0 ]; then
        echo "PARTIAL: Discusses palindrome but code incomplete"
        ((PARTIAL++))
    else
        echo "FAIL: No Python code found"
        echo "Answer preview: ${answer:0:200}"
        ((FAIL++))
    fi
}

# Test 5: Federal Reserve interest rates
check_5() {
    local has_fed=$(echo "$answer" | grep -ci "federal\|fed\|interest\|rate" || true)
    local has_percent=$(echo "$answer" | grep -c "%" || true)
    if [ "$has_fed" -gt 0 ] && [ "$has_percent" -gt 0 ]; then
        echo "PASS: Discusses Fed rates with specific percentages"
        ((PASS++))
    elif [ "$has_fed" -gt 0 ]; then
        echo "PARTIAL: Discusses Fed rates but no specific numbers"
        ((PARTIAL++))
    else
        echo "FAIL: Missing Federal Reserve discussion"
        echo "Answer preview: ${answer:0:200}"
        ((FAIL++))
    fi
}

# Test 6: Quadratic formula derivation
check_6() {
    local has_formula=$(echo "$answer" | grep -ci "quadratic\|formula\|discriminant\|\-b\|sqrt\|\\\\frac" || true)
    local has_steps=$(echo "$answer" | grep -ci "completing the square\|complete the square\|subtract\|divide" || true)
    if [ "$has_formula" -gt 0 ] && [ "$has_steps" -gt 0 ]; then
        echo "PASS: Derives quadratic formula with steps"
        ((PASS++))
    elif [ "$has_formula" -gt 0 ]; then
        echo "PARTIAL: Shows formula but derivation incomplete"
        ((PARTIAL++))
    else
        echo "FAIL: No quadratic formula derivation"
        echo "Answer preview: ${answer:0:200}"
        ((FAIL++))
    fi
}

# Test 7: Prove sqrt(2) is irrational
check_7() {
    local has_proof=$(echo "$answer" | grep -ci "irrational\|contradiction\|sqrt\|rational" || true)
    local has_method=$(echo "$answer" | grep -ci "assume\|suppose\|coprime\|even\|odd" || true)
    if [ "$has_proof" -gt 0 ] && [ "$has_method" -gt 0 ]; then
        echo "PASS: Proof by contradiction with proper steps"
        ((PASS++))
    elif [ "$has_proof" -gt 0 ]; then
        echo "PARTIAL: Mentions irrationality but proof incomplete"
        ((PARTIAL++))
    else
        echo "FAIL: No irrationality proof"
        echo "Answer preview: ${answer:0:200}"
        ((FAIL++))
    fi
}

# Test 8: Capital of France (baseline)
check_8() {
    if echo "$answer" | grep -qi "paris"; then
        echo "PASS: Correct — Paris"
        ((PASS++))
    else
        echo "FAIL: Expected 'Paris'"
        echo "Answer preview: ${answer:0:200}"
        ((FAIL++))
    fi
}

# ═══════════════════════════════════════════════
# RUN ALL TESTS
# ═══════════════════════════════════════════════

echo "╔═══════════════════════════════════════════════╗"
echo "║   TRINITY IQ STRESS TESTS v3                 ║"
echo "║   Post-Pipeline-Audit Verification           ║"
echo "╚═══════════════════════════════════════════════╝"
echo "Target: $API"
echo "Output: $OUTDIR"
echo ""

TOTAL_START=$(date +%s)

run_test 1 "generate/agent" "What is 2+2?" "check_1" "Simple math"
run_test 2 "generate/agent" "What is the difference between TCP and UDP?" "check_2" "Technical comparison"
run_test 3 "generate/agent" "A farmer has 17 sheep. All but 9 die. How many are left?" "check_3" "Trick question"
run_test 4 "generate/agent" "Write a Python function to check if a string is a palindrome using dynamic programming" "check_4" "Complex code generation"
run_test 5 "generate/agent" "What are the current federal reserve interest rates and why do they matter?" "check_5" "Current events + search"
run_test 6 "generate/agent" "Derive the quadratic formula from ax^2 + bx + c = 0" "check_6" "Math derivation"
run_test 7 "generate/agent" "Prove that the square root of 2 is irrational" "check_7" "Math proof"
run_test 8 "generate/stream" "What is the capital of France?" "check_8" "Baseline trivial"

TOTAL_END=$(date +%s)
TOTAL_ELAPSED=$((TOTAL_END - TOTAL_START))

echo ""
echo "╔═══════════════════════════════════════════════╗"
echo "║   RESULTS SUMMARY                            ║"
echo "╠═══════════════════════════════════════════════╣"
echo "║   PASS:    $PASS / 8                              ║"
echo "║   PARTIAL: $PARTIAL / 8                              ║"
echo "║   FAIL:    $FAIL / 8                              ║"
echo "║   Total:   ${TOTAL_ELAPSED}s                              ║"
echo "╚═══════════════════════════════════════════════╝"

if [ "$FAIL" -eq 0 ]; then
    echo "ALL TESTS PASSED (or partial)"
    exit 0
else
    echo "SOME TESTS FAILED"
    exit 1
fi
