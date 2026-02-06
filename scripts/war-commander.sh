#!/bin/bash

# ⚔️ WAR OF THREE KINGS - Battle Commander Script ⚔️
# This script automates health checks and warmup for all three kings

set -e

# Define colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# King endpoints
QWEN_URL="https://sptj5nup2lc939i2h4bhq532gs.ingress.quanglong.org"
LLAMA_URL="http://56oqg7o6n9fu53ijan3udmmb5o.ingress.h4i-dedicated.eu-sw-2.digitalfrontier.so"
MIXTRAL_URL="https://bnivii01v9bcbchrqtej5pmd0k.ingress.4090.akashgpu.com"

# Model names
QWEN_MODEL="qwen2.5:72b"
LLAMA_MODEL="llama3.3:70b"
MIXTRAL_MODEL="mixtral:8x22b"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║           ⚔️  WAR OF THREE KINGS - BATTLE COMMANDER ⚔️        ║"
echo "║                     $(date +%H:%M:%S)                              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

health_check() {
    local name=$1
    local url=$2
    local emoji=$3
    
    echo -n "$emoji $name: "
    
    response=$(curl -s --max-time 30 "$url/health" 2>&1)
    
    if echo "$response" | grep -q "502\|503\|504\|Bad Gateway"; then
        echo -e "${YELLOW}⏳ LOADING${NC} (model downloading)"
        return 1
    elif echo "$response" | grep -q "healthy\|status.*ok\|200"; then
        echo -e "${GREEN}✅ READY${NC}"
        return 0
    elif echo "$response" | grep -q "curl"; then
        echo -e "${RED}❌ UNREACHABLE${NC}"
        return 1
    else
        echo -e "${YELLOW}⚠️ UNKNOWN${NC}: $response"
        return 1
    fi
}

warmup_test() {
    local name=$1
    local url=$2
    local model=$3
    local emoji=$4
    
    echo ""
    echo "$emoji Testing $name warmup..."
    
    start_time=$(date +%s.%N)
    
    response=$(curl -s --max-time 120 -X POST "$url/generate" \
        -H "Content-Type: application/json" \
        -d "{\"model\": \"$model\", \"prompt\": \"Say 'I am ready for battle!' in exactly those words.\", \"stream\": false}" 2>&1)
    
    end_time=$(date +%s.%N)
    elapsed=$(echo "$end_time - $start_time" | bc)
    
    if echo "$response" | grep -qi "ready for battle\|I am ready"; then
        echo -e "   ${GREEN}✅ PASSED${NC} (${elapsed}s)"
        return 0
    elif echo "$response" | grep -q "502\|503"; then
        echo -e "   ${YELLOW}⏳ Still loading${NC}"
        return 1
    else
        echo -e "   ${YELLOW}⚠️ Response:${NC} $(echo "$response" | head -c 200)"
        return 1
    fi
}

run_single_iq_question() {
    local name=$1
    local url=$2
    local model=$3
    local prompt=$4
    local expected=$5
    
    echo -n "   Testing: "
    
    response=$(curl -s --max-time 60 -X POST "$url/generate" \
        -H "Content-Type: application/json" \
        -d "{\"model\": \"$model\", \"prompt\": \"$prompt\", \"stream\": false}" 2>&1)
    
    # Extract the response text
    answer=$(echo "$response" | grep -o '"response":"[^"]*"' | sed 's/"response":"//;s/"$//' | head -c 500)
    
    if echo "$answer" | grep -qi "$expected"; then
        echo -e "${GREEN}✅ CORRECT${NC}"
        return 0
    else
        echo -e "${RED}❌ WRONG${NC} (got: $(echo "$answer" | head -c 100))"
        return 1
    fi
}

# Main execution
case "${1:-status}" in
    status|health)
        echo "🏥 HEALTH CHECK"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        qwen_ok=0; llama_ok=0; mixtral_ok=0
        
        health_check "QWEN EMPEROR" "$QWEN_URL" "👑" && qwen_ok=1
        health_check "LLAMA LORD" "$LLAMA_URL" "🦙" && llama_ok=1
        health_check "MIXTRAL MAVEN" "$MIXTRAL_URL" "🔮" && mixtral_ok=1
        
        echo ""
        total=$((qwen_ok + llama_ok + mixtral_ok))
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "READY: $total/3 kings"
        
        if [ $total -eq 3 ]; then
            echo -e "${GREEN}🎺 ALL KINGS READY FOR BATTLE!${NC}"
        else
            echo -e "${YELLOW}⏳ Waiting for $(( 3 - total )) more king(s)...${NC}"
        fi
        ;;
        
    warmup)
        echo "🔥 WARMUP TESTS"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        
        warmup_test "QWEN EMPEROR" "$QWEN_URL" "$QWEN_MODEL" "👑"
        warmup_test "LLAMA LORD" "$LLAMA_URL" "$LLAMA_MODEL" "🦙"
        warmup_test "MIXTRAL MAVEN" "$MIXTRAL_URL" "$MIXTRAL_MODEL" "🔮"
        ;;
        
    iq-sample)
        echo "🧠 IQ TEST SAMPLE (3 questions)"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        
        for king_data in "QWEN:$QWEN_URL:$QWEN_MODEL:👑" "LLAMA:$LLAMA_URL:$LLAMA_MODEL:🦙" "MIXTRAL:$MIXTRAL_URL:$MIXTRAL_MODEL:🔮"; do
            IFS=':' read -r name url model emoji <<< "$king_data"
            echo ""
            echo "$emoji $name"
            run_single_iq_question "$name" "$url" "$model" "What is the square root of 144? Answer with just the number." "12"
            run_single_iq_question "$name" "$url" "$model" "A bat and a ball cost \$1.10. The bat costs \$1 more than the ball. How much does the ball cost?" "0.05"
            run_single_iq_question "$name" "$url" "$model" "How many r's in strawberry?" "3"
        done
        ;;
        
    *)
        echo "Usage: $0 {status|warmup|iq-sample}"
        echo ""
        echo "Commands:"
        echo "  status    - Check health of all kings"
        echo "  warmup    - Run warmup test on all kings"
        echo "  iq-sample - Run 3 IQ questions on all kings"
        ;;
esac

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Timestamp: $(date)"
