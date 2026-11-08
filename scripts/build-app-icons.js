// Rebuilds the favicon, home-screen icons, and README banner from assets/logo/, and a GitHub social
// preview image in design/ (upload that one by hand under Settings > General > Social preview).
//
// Run it after changing assets/logo/mark.svg or lockup.svg. It needs Playwright, so like the browser
// check it runs in the Playwright image, from the repository root:
//
//   docker run --rm -v "$PWD:/repo" -w /repo/tests/browser mcr.microsoft.com/playwright:v1.49.1-noble \
//     sh -c "npm install --silent --no-save playwright@1.49.1 && node ../../scripts/build-app-icons.js"

const fs = require("fs");
const path = require("path");
const { chromium } = require(require.resolve("playwright", { paths: [process.cwd()] }));

const ROOT = path.resolve(__dirname, "..");
const BG = "#071007"; // retro-crt, the default theme
const FG = "#9cff57";
const GLOW = "drop-shadow(0 0 6px rgba(156, 255, 87, 0.55))";

// The shapes inside a logo file, without its <svg> and <title>
const shapes = (name) => fs.readFileSync(path.join(ROOT, "assets", "logo", `${name}.svg`), "utf8")
    .replace(/^[\s\S]*?<\/title>/, "").replace(/<\/svg>\s*$/, "").trim();

// The mark centred on a dark 64 x 64 square, at `scale` of the square's size
function squareIcon(scale, rx) {
    const offset = +(32 - 32 * scale).toFixed(2);
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <title>Outpost</title>
  <rect width="64" height="64"${rx ? ` rx="${rx}"` : ""} fill="${BG}"/>
  <g fill="${FG}" transform="translate(${offset} ${offset}) scale(${scale})">
  ${shapes("mark")}
  </g>
</svg>
`;
}

const banner = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 72">
  <title>Outpost</title>
  <rect width="240" height="72" rx="6" fill="${BG}"/>
  <g fill="${FG}" transform="translate(15 2)">
  ${shapes("lockup")}
  </g>
</svg>
`;

(async () => {
    const write = (file, text) => {
        fs.mkdirSync(path.dirname(file), { recursive: true });
        fs.writeFileSync(file, text);
        console.log(`wrote ${path.relative(ROOT, file)}`);
    };
    write(path.join(ROOT, "assets", "app", "favicon.svg"), squareIcon(0.84, 12));
    write(path.join(ROOT, "docs", "images", "logo-banner.svg"), banner);

    const browser = await chromium.launch();
    const png = async (svg, size, name) => {
        const page = await browser.newPage({ viewport: { width: size, height: size } });
        await page.setContent(`<body style="margin:0">${svg.replace("<svg ", `<svg width="${size}" height="${size}" style="display:block" `)}</body>`);
        const file = path.join(ROOT, "assets", "app", name);
        await page.screenshot({ path: file });
        console.log(`wrote ${path.relative(ROOT, file)}`);
        await page.close();
    };
    // Square icons with no transparency: phones round the corners themselves
    await png(squareIcon(0.8), 192, "icon-192.png");
    await png(squareIcon(0.8), 512, "icon-512.png");
    await png(squareIcon(0.8), 180, "apple-touch-icon.png");
    // Android may crop a maskable icon to a circle: keep the plate inside the centre 80%
    await png(squareIcon(0.7), 512, "icon-maskable-512.png");

    const page = await browser.newPage({ viewport: { width: 1280, height: 640 } });
    await page.setContent(`<body style="margin:0;height:640px;background:${BG};color:${FG};display:grid;place-items:center">
      <div style="text-align:center;font:28px/1.4 monospace;letter-spacing:.12em">
        <svg viewBox="0 0 206 68" fill="currentColor" style="width:900px;filter:${GLOW}">${shapes("lockup")}</svg>
        <div style="opacity:.75;margin-top:8px">SELF-HOSTED WEATHER DASHBOARD</div>
      </div></body>`);
    const preview = path.join(ROOT, "design", "social-preview.png");
    fs.mkdirSync(path.dirname(preview), { recursive: true });
    await page.screenshot({ path: preview });
    console.log(`wrote ${path.relative(ROOT, preview)}`);
    await browser.close();
})().catch((error) => {
    console.error(error);
    process.exit(1);
});
