// WCAG 2.x contrast, for the design-token tests.
export function parseColour(colour) {
    const hex = /^#([0-9a-f]{6})$/i.exec(colour);
    if (hex) {
        const n = Number.parseInt(hex[1], 16);
        return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255, a: 1 };
    }
    const rgba = /^rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*(?:,\s*([\d.]+)\s*)?\)$/i.exec(colour);
    if (rgba) {
        return {
            r: Number(rgba[1]),
            g: Number(rgba[2]),
            b: Number(rgba[3]),
            a: rgba[4] === undefined ? 1 : Number(rgba[4]),
        };
    }
    throw new Error(`Unsupported colour: ${colour}`);
}
/** `top` painted over an opaque `bottom`. */
export function over(top, bottom) {
    const a = top.a;
    return {
        r: top.r * a + bottom.r * (1 - a),
        g: top.g * a + bottom.g * (1 - a),
        b: top.b * a + bottom.b * (1 - a),
        a: 1,
    };
}
function channel(value) {
    const c = value / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}
export function luminance(c) {
    return 0.2126 * channel(c.r) + 0.7152 * channel(c.g) + 0.0722 * channel(c.b);
}
export function contrast(a, b) {
    const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
    return (hi + 0.05) / (lo + 0.05);
}
