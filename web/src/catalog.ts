// Addresses for Apple Music catalog artwork and Apple's badge on Tandem's own server (the page
// may load images only from Tandem). Both need this launch's token from the page's address.

function token(search: string): string {
  return encodeURIComponent(new URLSearchParams(search).get("token") ?? "");
}

export function catalogArtUrl(search: string, id: string): string {
  return `/catalog-art/${encodeURIComponent(id)}?token=${token(search)}`;
}

export function badgeUrl(search: string): string {
  return `/apple-music-badge?token=${token(search)}`;
}
