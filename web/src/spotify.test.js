import { describe, expect, it } from "vitest";
import { itemDetail, looksLikeClientId, setupStep, spotifyArtUrl, targetName } from "./spotify";
import { spotifyErrorText } from "./strings";
function spotify(over = {}) {
    return {
        state: "signed_in",
        loading: false,
        redirectUri: "http://127.0.0.1/callback",
        error: null,
        playlists: [],
        devices: [
            { id: "d1", name: "Demo Laptop", kind: "computer", active: true, restricted: false },
            { id: "d2", name: "Example Phone", kind: "smartphone", active: false, restricted: false },
        ],
        target: "d2",
        query: "",
        searching: false,
        results: [],
        ...over,
    };
}
function item(over) {
    return { id: "t:1", kind: "track", title: "Song", subtitle: "", duration: null, hasArt: false, count: null, ...over };
}
describe("spotify helpers", () => {
    it("builds token-carrying artwork addresses", () => {
        expect(spotifyArtUrl("?token=a+b", "p:1 2")).toBe("/spotify-art/p%3A1%202?token=a%20b");
        expect(spotifyArtUrl("", "t:x")).toBe("/spotify-art/t%3Ax?token=");
    });
    it("describes items", () => {
        expect(itemDetail(item({ subtitle: "Artist · Album", duration: 201 }))).toBe("Artist · Album · 3:21");
        expect(itemDetail(item({ kind: "playlist", subtitle: "Demo User", count: 1 }))).toBe("Playlist · Demo User · 1 track");
        expect(itemDetail(item({ kind: "album", subtitle: "" }))).toBe("Album");
    });
    it("knows the next setup step", () => {
        expect(setupStep(spotify({ state: "not_set_up" }))).toBe("clientId");
        expect(setupStep(spotify({ state: "signed_out" }))).toBe("signIn");
        expect(setupStep(spotify({ state: "signing_in" }))).toBe("signIn");
        expect(setupStep(spotify())).toBe("done");
    });
    it("names the target device", () => {
        expect(targetName(spotify())).toBe("Example Phone");
        expect(targetName(spotify({ target: null }))).toBeNull();
    });
    it("checks Client IDs", () => {
        expect(looksLikeClientId(` ${"aB".repeat(16)} `)).toBe(true);
        expect(looksLikeClientId("abc")).toBe(false);
    });
    it("has words for every error", () => {
        const codes = [
            "invalid_client_id",
            "port_busy",
            "sign_in_timeout",
            "sign_in_denied",
            "sign_in_failed",
            "expired",
            "no_device",
            "premium_required",
            "not_allowed",
            "rate_limited",
            "unavailable",
            "gone",
            "vault",
        ];
        for (const code of codes)
            expect(spotifyErrorText(code, "http://127.0.0.1/callback")).toBeTruthy();
        expect(spotifyErrorText("sign_in_timeout", "X")).toContain("exactly X");
    });
});
