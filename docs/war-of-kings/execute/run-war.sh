#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# ⚔️  WAR OF THREE KINGS - MASTER COMMANDER ⚔️
# ═══════════════════════════════════════════════════════════════════════════════
#
# One script to rule them all. Execute the full tournament.
#
# Usage:
#   ./run-war.sh status      # Check if all kings are ready
#   ./run-war.sh warmup      # Warmup all kings
#   ./run-war.sh battle1     # Run IQ Test only
#   ./run-war.sh battle2     # Run General Spam only
#   ./run-war.sh battle3     # Run Complex Spam only
#   ./run-war.sh full        # Run ALL battles in sequence
#   ./run-war.sh export      # Compile all results for Claude
#
# ═══════════════════════════════════════════════════════════════════════════════

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="$SCRIPT_DIR/../results"

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
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'

print_banner() {
    echo ""
    echo "╔══════════════════════════════════════════════════════════════════╗"
    echo "║                                                                  ║"
    echo "║           ⚔️   W A R   O F   T H R E E   K I N G S   ⚔️          ║"
    echo "║                                                                  ║"
    echo "║     👑 Qwen Emperor    🦙 Llama Lord    🔮 Mixtral Maven        ║"
    echo "║                                                                  ║"
    echo "╚══════════════════════════════════════════════════════════════════╝"
    echo ""
}

check_health() {
    local name=$1
    local url=$2
    local emoji=$3
    
    echo -n "   $emoji $name: "
    
    local response=$(curl -s --max-time 10 "$url/health" 2>&1)
    
    if echo "$response" | grep -qi "healthy\|ok\|running"; then
        echo -e "${GREEN}✅ READY${NC}"
        return 0
    elif echo "$response" | grep -q "502\|503\|Bad Gateway"; then
        echo -e "${YELLOW}⏳ LOADING${NC}"
        return 1
    else
        echo -e "${RED}❌ DOWN${NC}"
        return 1
    fi
}

warmup_king() {
    local name=$1
    local url=$2
    local model=$3
    local emoji=$4
    
    echo -n "   $emoji $name: "
    
    local start=$(date +%s)
    local response=$(curl -s --max-time 120 -X POST "$url/generate" \
        -H "Content-Type: application/json" \
        -d "{\"model\": \"$model\", \"prompt\": \"Say 'I am ready for battle!' exactly.\", \"stream\": false}" 2>&1)
    local elapsed=$(($(date +%s) - start))
    
    if echo "$response" | grep -qi "ready for battle"; then
        echo -e "${GREEN}✅ WARMED UP${NC} (${elapsed}s)"
        return 0
    else
        echo -e "${RED}❌ FAILED${NC} (${elapsed}s)"
        return 1
    fi
}

status_check() {
    print_banner
    echo "🏥 HEALTH STATUS"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    local ready=0
    check_health "Qwen Emperor" "$QWEN_URL" "👑" && ((ready++))
    check_health "Llama Lord" "$LLAMA_URL" "🦙" && ((ready++))
    check_health "Mixtral Maven" "$MIXTRAL_URL" "🔮" && ((ready++))
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    if [ $ready -eq 3 ]; then
        echo -e "${GREEN}🎺 ALL KINGS READY FOR BATTLE!${NC}"
        echo ""
        echo "Commands:"
        echo "  ./run-war.sh warmup   # Warmup all kings"
        echo "  ./run-war.sh full     # Execute full tournament"
        return 0
    else
        echo -e "${YELLOW}⏳ Waiting for $((3 - ready)) king(s) to finish loading...${NC}"
        return 1
    fi
}

run_warmup() {
    print_banner
    echo "🔥 WARMUP PHASE"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    warmup_king "Qwen Emperor" "$QWEN_URL" "$QWEN_MODEL" "👑"
    warmup_king "Llama Lord" "$LLAMA_URL" "$LLAMA_MODEL" "🦙"
    warmup_king "Mixtral Maven" "$MIXTRAL_URL" "$MIXTRAL_MODEL" "🔮"
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

run_battle1() {
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo "          BATTLE 1: THE IQ TEST (25 Questions)"
    echo "═══════════════════════════════════════════════════════════════"
    echo ""
    
    bash "$SCRIPT_DIR/battle1-iq-test.sh" all
}

run_battle2() {
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo "       BATTLE 2: GENERAL KNOWLEDGE SPAM (Throughput)"
    echo "═══════════════════════════════════════════════════════════════"
    echo ""
    
    bash "$SCRIPT_DIR/battle2-general-spam.sh" all
}

run_battle3() {
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo "        BATTLE 3: COMPLEX KNOWLEDGE SPAM (Stress)"
    echo "═══════════════════════════════════════════════════════════════"
    echo ""
    
    bash "$SCRIPT_DIR/battle3-complex-spam.sh" all
}

run_full_tournament() {
    print_banner
    
    echo "🏁 FULL TOURNAMENT MODE"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "This will execute:"
    echo "  1. Warmup all kings"
    echo "  2. Battle 1: IQ Test (25 questions × 3 kings)"
    echo "  3. Battle 2: General Spam (4 concurrency levels × 3 kings)"
    echo "  4. Battle 3: Complex Spam (3 stress levels × 3 kings)"
    echo ""
    echo "Estimated time: 60-90 minutes"
    echo ""
    read -p "Press ENTER to begin the War of Three Kings..."
    
    local start_time=$(date +%s)
    
    # Phase 0: Warmup
    run_warmup
    sleep 5
    
    # Phase 1: IQ Test
    run_battle1
    sleep 10
    
    # Phase 2: General Spam
    run_battle2
    sleep 10
    
    # Phase 3: Complex Spam
    run_battle3
    
    local end_time=$(date +%s)
    local total_time=$(((end_time - start_time) / 60))
    
    echo ""
    echo "╔══════════════════════════════════════════════════════════════════╗"
    echo "║                                                                  ║"
    echo "║              🏆 TOURNAMENT COMPLETE! 🏆                          ║"
    echo "║                                                                  ║"
    echo "║        Total time: ${total_time} minutes                               ║"
    echo "║                                                                  ║"
    echo "║        Run: ./run-war.sh export                                 ║"
    echo "║        To compile results for Claude analysis                    ║"
    echo "║                                                                  ║"
    echo "╚══════════════════════════════════════════════════════════════════╝"
}

export_results() {
    print_banner
    echo "📊 EXPORTING RESULTS FOR CLAUDE ANALYSIS"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    local export_file="$RESULTS_DIR/CLAUDE_ANALYSIS_INPUT_$(date +%Y%m%d_%H%M%S).md"
    
    cat > "$export_file" << 'HEADER'
# War of Three Kings - Battle Results for Claude Analysis

## Tournament Summary
- **Date:** $(date)
- **Kings:** Qwen Emperor (72B), Llama Lord (70B), Mixtral Maven (8x22B)
- **Battles:** IQ Test, General Spam, Complex Spam

---

HEADER

    # Battle 1 Results
    echo "## BATTLE 1: IQ TEST RESULTS" >> "$export_file"
    echo "" >> "$export_file"
    
    for king in qwen llama mixtral; do
        echo "### ${king^^}" >> "$export_file"
        if [ -f "$RESULTS_DIR/raw/$king/battle1-iq/SUMMARY.json" ]; then
            cat "$RESULTS_DIR/raw/$king/battle1-iq/SUMMARY.json" >> "$export_file"
        fi
        echo "" >> "$export_file"
        echo "#### Individual Questions:" >> "$export_file"
        for q in "$RESULTS_DIR/raw/$king/battle1-iq/Q"*.json; do
            if [ -f "$q" ]; then
                echo "\`\`\`json" >> "$export_file"
                cat "$q" >> "$export_file"
                echo "\`\`\`" >> "$export_file"
            fi
        done
        echo "" >> "$export_file"
    done
    
    # Battle 2 Results
    echo "## BATTLE 2: GENERAL KNOWLEDGE SPAM RESULTS" >> "$export_file"
    echo "" >> "$export_file"
    
    for king in qwen llama mixtral; do
        echo "### ${king^^}" >> "$export_file"
        for summary in "$RESULTS_DIR/raw/$king/battle2-general/summary_c"*.json; do
            if [ -f "$summary" ]; then
                echo "\`\`\`json" >> "$export_file"
                cat "$summary" >> "$export_file"
                echo "\`\`\`" >> "$export_file"
            fi
        done
        echo "" >> "$export_file"
    done
    
    # Battle 3 Results
    echo "## BATTLE 3: COMPLEX KNOWLEDGE SPAM RESULTS" >> "$export_file"
    echo "" >> "$export_file"
    
    for king in qwen llama mixtral; do
        echo "### ${king^^}" >> "$export_file"
        for summary in "$RESULTS_DIR/raw/$king/battle3-complex/summary_c"*.json; do
            if [ -f "$summary" ]; then
                echo "\`\`\`json" >> "$export_file"
                cat "$summary" >> "$export_file"
                echo "\`\`\`" >> "$export_file"
            fi
        done
        
        # Include sample responses for quality assessment
        echo "#### Sample Complex Responses:" >> "$export_file"
        local latest=$(ls -t "$RESULTS_DIR/raw/$king/battle3-complex/complex_c"*.jsonl 2>/dev/null | head -1)
        if [ -f "$latest" ]; then
            head -5 "$latest" >> "$export_file"
        fi
        echo "" >> "$export_file"
    done
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo -e "${GREEN}✅ Results exported to:${NC}"
    echo "   $export_file"
    echo ""
    echo "Next steps:"
    echo "  1. Open the export file"
    echo "  2. Copy contents to Claude"
    echo "  3. Include the judge prompt from:"
    echo "     docs/war-of-kings/prompts/claude-judge-prompt.md"
    echo ""
}

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

case "${1:-help}" in
    status)
        status_check
        ;;
    warmup)
        run_warmup
        ;;
    battle1|iq)
        run_battle1
        ;;
    battle2|general)
        run_battle2
        ;;
    battle3|complex)
        run_battle3
        ;;
    full|all)
        run_full_tournament
        ;;
    export)
        export_results
        ;;
    help|*)
        print_banner
        echo "COMMANDS:"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "  status    Check if all kings are ready"
        echo "  warmup    Warmup all kings with simple prompt"
        echo "  battle1   Run Battle 1: IQ Test (25 questions)"
        echo "  battle2   Run Battle 2: General Knowledge Spam"
        echo "  battle3   Run Battle 3: Complex Knowledge Spam"
        echo "  full      Run complete tournament (all battles)"
        echo "  export    Compile results for Claude analysis"
        echo ""
        echo "EXAMPLES:"
        echo "  ./run-war.sh status     # Check king health"
        echo "  ./run-war.sh full       # Run everything"
        echo ""
        ;;
esac
