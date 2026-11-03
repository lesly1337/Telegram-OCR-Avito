import os
import cv2
import pytesseract
from app.ocr.engine import reader

IMG = "fixtures/test_image.jpg"
OUT = "data/tmp"
ALLOW = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/:-. "

# Доли от размера кадра: (x1, y1, x2, y2)
CROPS = {
    "imei_row": (0.396, 0.615, 0.820, 0.659),  # IMEI 1 + IMEI 2
    "sn_row":   (0.610, 0.667, 0.826, 0.707),  # S/N
}

img = cv2.imread(IMG, cv2.IMREAD_GRAYSCALE)
H, W = img.shape
print(f"Размер кадра: {W}x{H}  (если не 720x540, координаты съехали)")

os.makedirs(OUT, exist_ok=True)

for name, (fx1, fy1, fx2, fy2) in CROPS.items():
    crop = img[int(fy1 * H):int(fy2 * H), int(fx1 * W):int(fx2 * W)]
    for scale in (4, 6, 8):
        big = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_LANCZOS4)
        inv = cv2.bitwise_not(big)
        _, otsu = cv2.threshold(inv, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        otsu = cv2.copyMakeBorder(otsu, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
        inv = cv2.copyMakeBorder(inv, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)

        for mode, arr in (("inv", inv), ("otsu", otsu)):
            cv2.imwrite(f"{OUT}/probe_{name}_x{scale}_{mode}.png", arr)
            t = pytesseract.image_to_string(
                arr, lang="eng",
                config=f"--oem 3 --psm 7 -c tessedit_char_whitelist={ALLOW}",
            ).strip()
            e = " ".join(reader.readtext(arr, detail=0, allowlist=ALLOW)).strip()
            print(f"{name:9} x{scale} {mode:5} | tess: {t!r:45} | easy: {e!r}")