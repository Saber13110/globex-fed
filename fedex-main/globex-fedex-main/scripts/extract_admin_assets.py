"""Extract Globex admin dashboard assets from reference sheet."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

SRC = Path(
    r"C:\Users\HP\.cursor\projects\c-Users-HP-globex-fedex\assets"
    r"\c__Users_HP_AppData_Roaming_Cursor_User_workspaceStorage_20e08879129df7b34dbacce4fa10ca25_images"
    r"_ChatGPT_Image_2_juin_2026__23_06_13-3d14559d-fa5e-40c2-8c8e-b1c8d2e729e4.png"
)
OUT = Path(__file__).resolve().parents[1] / "frontend" / "src" / "assets" / "admin"


def crop(im: Image.Image, box: tuple[int, int, int, int]) -> Image.Image:
    return im.crop(box)


def resize(im: Image.Image, size: tuple[int, int]) -> Image.Image:
    return im.resize(size, Image.Resampling.LANCZOS)


def transparent_black(im: Image.Image, threshold: int = 32) -> Image.Image:
    rgba = im.convert("RGBA")
    px = rgba.load()
    w, h = rgba.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if r <= threshold and g <= threshold and b <= threshold:
                px[x, y] = (0, 0, 0, 0)
    return rgba


def trim(im: Image.Image) -> Image.Image:
    bbox = im.getbbox()
    return im.crop(bbox) if bbox else im


def circle_avatar(im: Image.Image, size: int = 512) -> Image.Image:
    fitted = ImageOps.fit(im.convert("RGBA"), (size, size), Image.Resampling.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(fitted, (0, 0), mask)
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    im = Image.open(SRC).convert("RGB")
    w, h = im.size
    print(f"Source {w}x{h}")

    # Layout tuned for 1024x682 sheet (hero top, brain mid-right, avatar bottom-left, KPIs bottom-right)
    exports: list[tuple[str, tuple, tuple, bool]] = [
        ("hero-banner.png", (6, 38, w - 6, 232), (1920, 600), False),
        ("ai-brain.png", (520, 248, w - 8, 455), (800, 800), True),
        ("avatar-executive.png", (22, 478, 310, 672), (512, 512), False),
    ]
    for name, box, size, transparent in exports:
        piece = crop(im, box)
        if transparent:
            piece = trim(transparent_black(piece))
        piece = resize(piece, size)
        if name == "avatar-executive.png":
            piece = circle_avatar(piece, 512)
        piece.save(OUT / name, optimize=True)
        print(f"  {name} {size}")

    kpi_region = crop(im, (340, 478, w - 10, h - 8))
    kw, kh = kpi_region.size
    slots = [
        ("kpi-shipments.png", (0.05, 0.0, 0.38, 0.48)),
        ("kpi-deliveries.png", (0.36, 0.0, 0.62, 0.48)),
        ("kpi-users.png", (0.60, 0.0, 0.88, 0.48)),
        ("kpi-incidents.png", (0.30, 0.46, 0.72, 1.0)),
    ]
    for fname, (x0f, y0f, x1f, y1f) in slots:
        box = (int(kw * x0f), int(kh * y0f), int(kw * x1f), int(kh * y1f))
        icon = trim(transparent_black(crop(kpi_region, box)))
        icon = resize(icon, (256, 256))
        icon.save(OUT / fname, optimize=True)
        print(f"  {fname}")

    # World map from hero crop left portion
    hero = crop(im, (6, 38, w - 6, 232))
    map_part = crop(hero, (0, 0, int(hero.width * 0.55), hero.height))
    map_part = transparent_black(map_part, 40)
    map_part = trim(map_part)
    map_part = resize(map_part, (1400, 300))
    map_part.save(OUT / "world-map-overlay.png", optimize=True)
    print("  world-map-overlay.png")

    im.save(OUT / "assets-sheet.png", optimize=True)
    print("Done")


if __name__ == "__main__":
    main()
