"""Writes barcode.y4m (fake camera for check_staff_browser.py): EAN-13 9781234567897,
added as a PKT barcode of KGS-T-BOOK1 on the dev site. Run with the bench python (needs Pillow)."""
import os

from PIL import Image, ImageDraw

L = {"0": "0001101", "1": "0011001", "2": "0010011", "3": "0111101", "4": "0100011", "5": "0110001", "6": "0101111", "7": "0111011", "8": "0110111", "9": "0001011"}
G = {"0": "0100111", "1": "0110011", "2": "0011011", "3": "0100001", "4": "0011101", "5": "0111001", "6": "0000101", "7": "0010001", "8": "0001001", "9": "0010111"}
R = {k: "".join("1" if c == "0" else "0" for c in v) for k, v in L.items()}
P = {"0": "LLLLLL", "1": "LLGLGG", "2": "LLGGLG", "3": "LLGGGL", "4": "LGLLGG", "5": "LGGLLG", "6": "LGGGLL", "7": "LGLGLG", "8": "LGLGGL", "9": "LGGLGL"}
code = "9781234567897"
bits = "101" + "".join((L if p == "L" else G)[c] for p, c in zip(P[code[0]], code[1:7])) + "01010" + "".join(R[c] for c in code[7:]) + "101"
W, H, mw = 640, 480, 5
im = Image.new("L", (W, H), 235)
dr = ImageDraw.Draw(im)
x0 = (W - len(bits) * mw) // 2
dr.rectangle([x0 - 40, 120, x0 + len(bits) * mw + 40, 360], fill=255)
for i, b in enumerate(bits):
	if b == "1":
		dr.rectangle([x0 + i * mw, 140, x0 + i * mw + mw - 1, 340], fill=0)
uv = bytes([128]) * ((W // 2) * (H // 2))
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "barcode.y4m"), "wb") as f:
	f.write(f"YUV4MPEG2 W{W} H{H} F10:1 Ip A1:1 C420jpeg\n".encode())
	for _ in range(10):
		f.write(b"FRAME\n" + im.tobytes() + uv + uv)
