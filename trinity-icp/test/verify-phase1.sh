#!/bin/bash
set -e

echo "🧪 Phase 1 Verification Starting..."
echo ""
echo "⚠️  Manual tests required. Please follow the prompts."
echo ""

# 1. Test login
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1️⃣  Testing Login Flow"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   📋 Steps:"
echo "      1. Open your browser to the Trinity app"
echo "      2. Click 'Create New Identity' button"
echo "      3. Verify modal shows your Principal ID"
echo "      4. Check sidebar shows green checkmark with Principal"
echo ""
read -p "   ✓ Did login work correctly? (y/n): " login_ok
if [[ $login_ok != "y" ]]; then
    echo "❌ Login test failed"
    exit 1
fi
echo "   ✅ Login test PASSED"
echo ""

# 2. Test chat creation
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2️⃣  Testing Chat Creation"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   📋 Steps:"
echo "      1. Type a message: 'Hello, this is a test!'"
echo "      2. Click Send button (or press Enter)"
echo "      3. Wait for AI response"
echo "      4. Verify your message appears in chat"
echo "      5. Verify AI response appears below it"
echo ""
read -p "   ✓ Did chat creation work? (y/n): " chat_ok
if [[ $chat_ok != "y" ]]; then
    echo "❌ Chat creation test failed"
    exit 1
fi
echo "   ✅ Chat creation test PASSED"
echo ""

# 3. Test autosave
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3️⃣  Testing Autosave"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   📋 Steps:"
echo "      1. Wait 3-4 seconds after AI responds"
echo "      2. Look for autosave indicator (if visible)"
echo "      3. Hard refresh the page (Cmd+Shift+R or Ctrl+Shift+R)"
echo "      4. Check sidebar - chat should appear in 'Active Chats'"
echo "      5. Click on the chat to load it"
echo "      6. Verify your conversation is restored"
echo ""
read -p "   ✓ Did autosave work? (y/n): " autosave_ok
if [[ $autosave_ok != "y" ]]; then
    echo "❌ Autosave test failed"
    exit 1
fi
echo "   ✅ Autosave test PASSED"
echo ""

# 4. Test archive
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4️⃣  Testing Archive"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   📋 Steps:"
echo "      1. Find the archive button (📦) on an active chat"
echo "      2. Click the archive button"
echo "      3. Confirm the archive action"
echo "      4. Verify chat moves to 'ARCHIVED CHATS' section (purple border)"
echo "      5. Verify the chat count shows (N/10)"
echo "      6. If this was your active chat, verify new chat started automatically"
echo ""
read -p "   ✓ Did archive work? (y/n): " archive_ok
if [[ $archive_ok != "y" ]]; then
    echo "❌ Archive test failed"
    exit 1
fi
echo "   ✅ Archive test PASSED"
echo ""

# 5. Test load archived chat
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "5️⃣  Testing Load Archived Chat"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   📋 Steps:"
echo "      1. Click on the archived chat you just created"
echo "      2. Verify all messages load correctly"
echo "      3. Verify input field is DISABLED"
echo "      4. Verify send button is DISABLED"
echo "      5. Verify warning message shows '📦 Archived chat (read-only)'"
echo ""
read -p "   ✓ Did loading archived chat work? (y/n): " load_ok
if [[ $load_ok != "y" ]]; then
    echo "❌ Load archived chat test failed"
    exit 1
fi
echo "   ✅ Load archived chat test PASSED"
echo ""

# 6. Test user memory
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "6️⃣  Testing User Memory"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   📋 Steps:"
echo "      1. Click the purple '🧠 Memory' button in sidebar"
echo "      2. Add a fact: 'My name is Trinity Tester'"
echo "      3. Close the memory modal"
echo "      4. Click 'New Chat' button"
echo "      5. In the new chat, ask: 'What is my name?'"
echo "      6. Wait for AI response"
echo "      7. Verify AI mentions 'Trinity Tester' in response"
echo ""
read -p "   ✓ Did user memory work? (y/n): " memory_ok
if [[ $memory_ok != "y" ]]; then
    echo "❌ User memory test failed"
    exit 1
fi
echo "   ✅ User memory test PASSED"
echo ""

# All tests passed
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅✅✅ Phase 1 Verification COMPLETE ✅✅✅"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📊 Summary:"
echo "   ✅ Login flow"
echo "   ✅ Chat creation"
echo "   ✅ Autosave"
echo "   ✅ Archive"
echo "   ✅ Load archived chat"
echo "   ✅ User memory"
echo ""
echo "🎉 All 6 manual tests PASSED!"
echo ""
echo "📝 Next Steps:"
echo "   1. Run: npm test"
echo "   2. Check coverage: npm run test:coverage"
echo "   3. Verify syntax: node -c src/trinity_frontend/assets/app.js"
echo "   4. If all pass, proceed to Phase 2"
echo ""
exit 0
