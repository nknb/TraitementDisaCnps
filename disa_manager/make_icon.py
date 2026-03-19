"""
make_icon.py — Convertit cnps_logo.jpeg en cnps_logo.ico
Usage : python make_icon.py
Requis : pip install Pillow
"""
from pathlib import Path
import sys

SRC  = Path("src/ui/images/cnps_logo.jpeg")
DEST = Path("src/ui/images/cnps_logo.ico")

# Tailles standard Windows pour une icône multi-résolution
SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def main() -> None:
    try:
        from PIL import Image
    except ImportError:
        print("[ERREUR] Pillow n'est pas installé.")
        print("         Installez-le avec : pip install Pillow")
        sys.exit(1)

    if not SRC.exists():
        print(f"[ERREUR] Fichier source introuvable : {SRC}")
        sys.exit(1)

    img = Image.open(SRC).convert("RGBA")

    # Rognage carré centré (l'icône doit être carrée)
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top  = (h - side) // 2
    img  = img.crop((left, top, left + side, top + side))

    # Générer les miniatures pour chaque taille
    imgs = [img.resize(s, Image.LANCZOS) for s in SIZES]

    imgs[0].save(
        DEST,
        format="ICO",
        sizes=SIZES,
        append_images=imgs[1:],
    )
    print(f"[OK] Icône générée : {DEST}")
    print(f"     Tailles incluses : {', '.join(f'{s[0]}×{s[1]}' for s in SIZES)}")


if __name__ == "__main__":
    main()
