import { describe, expect, it } from "vitest";
import { badgeUrl, catalogArtUrl } from "./catalog";
describe("catalog addresses", () => {
    it("carry the page's token", () => {
        expect(catalogArtUrl("?token=a+b", "s 1")).toBe("/catalog-art/s%201?token=a%20b");
        expect(badgeUrl("?token=x")).toBe("/apple-music-badge?token=x");
        expect(badgeUrl("")).toBe("/apple-music-badge?token=");
    });
});
