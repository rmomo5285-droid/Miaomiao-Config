import manifest from "./public/manifest.json";

const manifestBody = JSON.stringify(manifest);
const responseHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Cache-Control": "public, max-age=300, s-maxage=300, must-revalidate",
  "Content-Type": "application/json; charset=utf-8",
  "X-Content-Type-Options": "nosniff",
};

export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (url.pathname !== "/json" && url.pathname !== "/json/") {
      return new Response("Not found", { status: 404 });
    }
    if (request.method !== "GET" && request.method !== "HEAD") {
      return new Response("Method not allowed", {
        status: 405,
        headers: { Allow: "GET, HEAD" },
      });
    }
    return new Response(request.method === "HEAD" ? null : manifestBody, {
      status: 200,
      headers: responseHeaders,
    });
  },
};
