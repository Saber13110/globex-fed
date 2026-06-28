"""
Supprime le fond lavande du PNG hero-plane.png et sauve une version transparente.

Stratégie :
1. Sample la couleur du coin haut-gauche (background pur)
2. Pour chaque pixel, calcule la distance euclidienne avec ce sample
3. Si proche du background → met alpha=0 (transparent)
4. Si loin (plane, trail, clouds) → garde le pixel intact
5. Zone de transition douce pour les anti-alias edges
"""

from pathlib import Path
from PIL import Image
import math

SRC = Path(__file__).resolve().parents[2] / "frontend" / "src" / "assets" / "hero-plane.png"
DST = Path(__file__).resolve().parents[2] / "frontend" / "src" / "assets" / "hero-plane.png"

# Tolérance : pixels à distance < TOLERANCE_HARD du bg → 100% transparent
# Pixels entre TOLERANCE_HARD et TOLERANCE_SOFT → alpha graduel (anti-alias)
TOLERANCE_HARD = 18  # ajustable
TOLERANCE_SOFT = 45  # ajustable


def color_distance(c1, c2):
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(c1[:3], c2[:3])))


def main():
    img = Image.open(SRC).convert("RGBA")
    print(f"Image chargée : {img.size}, mode={img.mode}")

    # Sample background = moyenne des 4 coins (plus robuste qu'un seul pixel)
    w, h = img.size
    corners = [
        img.getpixel((0, 0)),
        img.getpixel((w - 1, 0)),
        img.getpixel((0, h - 1)),
        img.getpixel((w - 1, h - 1)),
    ]
    bg = tuple(int(sum(c[i] for c in corners) / 4) for i in range(3))
    print(f"Couleur background detectee : RGB{bg} -> #{bg[0]:02x}{bg[1]:02x}{bg[2]:02x}")

    pixels = img.load()
    transparent_count = 0
    soft_count = 0

    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            dist = color_distance((r, g, b), bg)

            if dist < TOLERANCE_HARD:
                pixels[x, y] = (r, g, b, 0)
                transparent_count += 1
            elif dist < TOLERANCE_SOFT:
                # Anti-alias edges : alpha interpolé
                ratio = (dist - TOLERANCE_HARD) / (TOLERANCE_SOFT - TOLERANCE_HARD)
                new_alpha = int(a * ratio)
                pixels[x, y] = (r, g, b, new_alpha)
                soft_count += 1

    total = w * h
    print(f"Pixels traites : {total}")
    print(f"  -> 100% transparents : {transparent_count} ({transparent_count*100/total:.1f}%)")
    print(f"  -> anti-alias graduel : {soft_count} ({soft_count*100/total:.1f}%)")
    print(f"  -> intacts (plane) : {total - transparent_count - soft_count}")

    # Backup original avant écrasement
    backup = SRC.with_name(SRC.stem + "_original.png")
    if not backup.exists():
        Image.open(SRC).save(backup)
        print(f"Backup créé : {backup.name}")

    img.save(DST, "PNG", optimize=True)
    print(f"\n[OK] Image transparente sauvee : {DST}")


if __name__ == "__main__":
    main()
