// ============================================================================
// RAINBOW BORDER ANIMATION HANDLER
// ============================================================================
// Handles mouse-position-aware rainbow border animation for buttons
// Calculates entry angle based on mouse position and animates trail from that point

export default function initRainbowBorders() {
    document.addEventListener('mouseover', (e) => {
        const btn = e.target.closest('.rainbow-border-btn');
        if (!btn) return;

        // Get button position and dimensions
        const rect = btn.getBoundingClientRect();
        const centerX = rect.left + rect.width / 2;
        const centerY = rect.top + rect.height / 2;

        // Calculate angle from center to mouse entry point
        const mouseX = e.clientX;
        const mouseY = e.clientY;
        const deltaX = mouseX - centerX;
        const deltaY = mouseY - centerY;
        
        // Convert to degrees (0° = right, 90° = bottom, 180° = left, 270° = top)
        let angle = Math.atan2(deltaY, deltaX) * (180 / Math.PI);
        // Normalize to 0-360 range
        angle = (angle + 360) % 360;

        // Set CSS custom property for starting angle
        btn.style.setProperty('--start-angle', `${angle}deg`);
        
        // Force animation restart by removing and re-adding class
        btn.classList.remove('rainbow-active');
        void btn.offsetWidth; // Trigger reflow
        btn.classList.add('rainbow-active');
    });

    document.addEventListener('mouseout', (e) => {
        const btn = e.target.closest('.rainbow-border-btn');
        if (!btn) return;
        
        // Remove active class to stop animation
        btn.classList.remove('rainbow-active');
    });
}
