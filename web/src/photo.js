// The user's own background photo: shrink it, re-encode it as a JPEG (which also drops the
// camera and location details a photo carries), and hand it to Tandem. The photo is personal:
// never log it.
/** The longest side Tandem keeps: sharp on a 4K screen, about half a megabyte. */
export const MAX_SIDE = 2560;
/** The size to draw a `width` x `height` picture at, no side longer than `MAX_SIDE`. */
export function fitWithin(width, height, max = MAX_SIDE) {
    const scale = Math.min(1, max / Math.max(width, height));
    return { width: Math.max(1, Math.round(width * scale)), height: Math.max(1, Math.round(height * scale)) };
}
async function toJpeg(file) {
    const bitmap = await createImageBitmap(file);
    try {
        const size = fitWithin(bitmap.width, bitmap.height);
        const canvas = document.createElement("canvas");
        canvas.width = size.width;
        canvas.height = size.height;
        const context = canvas.getContext("2d");
        if (!context)
            throw new Error("no canvas");
        context.drawImage(bitmap, 0, 0, size.width, size.height);
        return await new Promise((resolve, reject) => canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("no jpeg"))), "image/jpeg", 0.85));
    }
    finally {
        bitmap.close();
    }
}
/** Send `file` to Tandem as the background. True if Tandem took it. */
export async function uploadPhoto(file, search = window.location.search) {
    try {
        const jpeg = await toJpeg(file);
        const token = new URLSearchParams(search).get("token") ?? "";
        const response = await fetch(`/background?token=${encodeURIComponent(token)}`, {
            method: "POST",
            headers: { "Content-Type": "image/jpeg" },
            body: jpeg,
        });
        return response.ok;
    }
    catch {
        return false;
    }
}
