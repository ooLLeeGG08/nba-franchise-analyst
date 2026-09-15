// Several teams' official brand colors are pure black or otherwise too dark
// to read as text/borders on this app's near-black surface (e.g. the Spurs'
// and Bulls' secondary color, the Nets' primary color, are all #000000).
// This picks a readable substitute for foreground use while leaving the true
// brand color available for background swatches (hero gradients, badges),
// where a dark color is fine.
const TeamColors = (() => {
    function luminance(hex) {
        const rgb = hex.replace('#', '').match(/.{2}/g).map((h) => parseInt(h, 16) / 255);
        const [r, g, b] = rgb.map((c) => (c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4)));
        return 0.2126 * r + 0.7152 * g + 0.0722 * b;
    }

    function readableOnDark(hex, fallback = '#c9ccd1') {
        return luminance(hex) < 0.25 ? fallback : hex;
    }

    function contrastText(hex) {
        return luminance(hex) < 0.5 ? '#f2f3f5' : '#0a0c0f';
    }

    return { luminance, readableOnDark, contrastText };
})();
