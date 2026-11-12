import { describe, expect, it } from "vitest";
import { albumArtUrl, currentItem, folderName, groupByArtist, isSaved, playerPosition, stationDetails, upNext, } from "./library";
// Invented music (docs/PRIVACY.md).
const album = (id, artist) => ({
    id,
    title: `Album ${id}`,
    artist,
    year: null,
    trackCount: 3,
    hasArt: false,
});
const player = {
    state: "playing",
    index: 1,
    position: 30,
    duration: 200,
    error: false,
    queue: [
        { id: "q1", title: "One", kind: "file", artist: null, album: null, art: null },
        { id: "q2", title: "Two", kind: "file", artist: null, album: null, art: null },
        { id: "q3", title: "Three", kind: "file", artist: null, album: null, art: null },
    ],
};
const station = {
    id: "s1",
    name: "Example FM",
    codec: "MP3",
    bitrate: 128,
    country: "US",
    tags: "jazz",
};
describe("albumArtUrl", () => {
    it("carries the token and escapes the id", () => {
        expect(albumArtUrl("?token=a/b", "x y")).toBe("/library-art/x%20y?token=a%2Fb");
    });
});
describe("groupByArtist", () => {
    it("groups albums, artists in order, unknown last", () => {
        const groups = groupByArtist([album("1", "zed"), album("2", null), album("3", "Abe"), album("4", "Zed")]);
        expect(groups.map((g) => g.name)).toEqual(["Abe", "zed", null]);
        expect(groups[1]?.albums.map((a) => a.id)).toEqual(["1", "4"]);
    });
});
describe("the queue", () => {
    it("knows the current track and what follows", () => {
        expect(currentItem(player)?.title).toBe("Two");
        expect(upNext(player).map((q) => q.title)).toEqual(["Three"]);
        expect(currentItem({ ...player, index: null })).toBeNull();
        expect(upNext({ ...player, index: null })).toHaveLength(3);
        expect(currentItem({ ...player, index: 9 })).toBeNull();
    });
    it("counts on while playing, up to the end", () => {
        expect(playerPosition(player, 5)).toBe(35);
        expect(playerPosition(player, 999)).toBe(200);
        expect(playerPosition({ ...player, state: "paused" }, 5)).toBe(30);
        expect(playerPosition({ ...player, duration: null }, 5)).toBe(35);
        expect(playerPosition(player, -3)).toBe(30);
    });
});
describe("stations and folders", () => {
    it("describes a station with what's known", () => {
        const kbps = (n) => `${n} kbps`;
        expect(stationDetails(station, kbps)).toBe("MP3 · 128 kbps · US");
        expect(stationDetails({ ...station, bitrate: 0, country: "" }, kbps)).toBe("MP3");
        expect(isSaved([station], "s1")).toBe(true);
        expect(isSaved([], "s1")).toBe(false);
    });
    it("shortens a folder to its last part", () => {
        expect(folderName("C:\\Music\\Example Band\\")).toBe("Example Band");
        expect(folderName("D:/Media/Music")).toBe("Music");
        expect(folderName("")).toBe("");
    });
});
