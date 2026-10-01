"""PackNine 앱 아이콘(.ico/.icns) 생성 스크립트.

Pillow만으로 벡터 아트웍 없이 아이콘을 그린다. 실행 시
packnine/presentation/gui/assets/ 아래에 icon.ico(Windows, 다중 해상도),
icon.icns(macOS, 다중 해상도)와 icon_256.png(README/문서용 미리보기)를 생성한다.
Pillow의 ICNS 인코더는 순수 포맷 변환이라 macOS가 아닌 Windows에서도 생성 가능하다
(iconutil 등 macOS 전용 도구 불필요).

실행: .venv\\Scripts\\python.exe scripts\\generate_icon.py
"""
from __future__ import annotations

import pathlib

from PIL import Image, ImageDraw, ImageFont

ASSETS_DIR = pathlib.Path(__file__).resolve().parent.parent / "packnine" / "presentation" / "gui" / "assets"
CANVAS = 1024

# 브랜드 컬러: 인디고 -> 바이올렛 대각선 그라디언트 (압축/패키징 느낌의 차분하고 현대적인 톤)
GRADIENT_TOP_LEFT = (79, 70, 229)      # #4F46E5
GRADIENT_BOTTOM_RIGHT = (168, 85, 247)  # #A855F7
GLYPH_WHITE = (255, 255, 255, 255)
BADGE_BG = (17, 24, 39, 255)           # #111827


def _rounded_gradient_background(size: int) -> Image.Image:
    base = Image.new("RGB", (size, size))
    px = base.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * size)  # 좌상단(0) -> 우하단(1) 대각선 보간 계수
            r = int(GRADIENT_TOP_LEFT[0] + (GRADIENT_BOTTOM_RIGHT[0] - GRADIENT_TOP_LEFT[0]) * t)
            g = int(GRADIENT_TOP_LEFT[1] + (GRADIENT_BOTTOM_RIGHT[1] - GRADIENT_TOP_LEFT[1]) * t)
            b = int(GRADIENT_TOP_LEFT[2] + (GRADIENT_BOTTOM_RIGHT[2] - GRADIENT_TOP_LEFT[2]) * t)
            px[x, y] = (r, g, b)

    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    radius = int(size * 0.22)
    mask_draw.rounded_rectangle([(0, 0), (size - 1, size - 1)], radius=radius, fill=255)

    rgba = Image.new("RGBA", (size, size))
    rgba.paste(base, (0, 0), mask)
    return rgba


def _draw_archive_glyph(canvas: Image.Image) -> None:
    """압축 상자(box) + 지퍼 라인 형태의 심볼을 중앙에 그린다."""
    size = canvas.size[0]
    draw = ImageDraw.Draw(canvas)

    box_w = size * 0.46
    box_h = size * 0.40
    cx, cy = size / 2, size / 2 + size * 0.02
    left, top = cx - box_w / 2, cy - box_h / 2
    right, bottom = cx + box_w / 2, cy + box_h / 2

    # 상자 본체 (둥근 사각형 외곽선, 두꺼운 스트로크)
    stroke = max(6, int(size * 0.028))
    draw.rounded_rectangle(
        [(left, top), (right, bottom)], radius=size * 0.045,
        outline=GLYPH_WHITE, width=stroke,
    )

    # 상자 뚜껑 접힘선 (상단에서 약간 내려온 수평선)
    lid_y = top + box_h * 0.28
    draw.line([(left + stroke, lid_y), (right - stroke, lid_y)], fill=GLYPH_WHITE, width=stroke)

    # 압축(지퍼) 표시: 세로 중앙선 + 갈매기(chevron) 두 개
    zip_top, zip_bottom = lid_y, bottom - stroke
    draw.line([(cx, zip_top), (cx, zip_bottom)], fill=GLYPH_WHITE, width=max(4, int(size * 0.012)))
    chevron_w = size * 0.045
    for frac in (0.42, 0.62, 0.82):
        cyz = zip_top + (zip_bottom - zip_top) * frac
        draw.line([(cx - chevron_w, cyz - chevron_w), (cx, cyz)], fill=GLYPH_WHITE, width=max(4, int(size * 0.012)))
        draw.line([(cx + chevron_w, cyz - chevron_w), (cx, cyz)], fill=GLYPH_WHITE, width=max(4, int(size * 0.012)))

    # 우하단 "9" 뱃지
    badge_r = size * 0.15
    badge_cx, badge_cy = right - badge_r * 0.35, bottom - badge_r * 0.15
    draw.ellipse(
        [(badge_cx - badge_r, badge_cy - badge_r), (badge_cx + badge_r, badge_cy + badge_r)],
        fill=BADGE_BG,
    )
    font = _load_font(int(badge_r * 1.25))
    text = "9"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((badge_cx - tw / 2 - bbox[0], badge_cy - th / 2 - bbox[1]), text, font=font, fill=GLYPH_WHITE)


def _load_font(px_size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        r"C:\Windows\Fonts\seguisb.ttf",
        r"C:\Windows\Fonts\arialbd.ttf",
        r"C:\Windows\Fonts\segoeuib.ttf",
    ]
    for path in candidates:
        if pathlib.Path(path).exists():
            return ImageFont.truetype(path, px_size)
    return ImageFont.load_default(size=px_size)


def _clean_alpha(image: Image.Image) -> Image.Image:
    """거의 투명한 픽셀을 완전 투명으로 만들고 그 자리의 색을 지운다.

    둥근 모서리를 작은 크기로 줄이면 모서리에 알파가 3 정도인 색 픽셀이 남는다.
    이런 픽셀은 렌더링 경로에 따라 색이 비쳐 보여서, 작업 표시줄 아이콘 네 귀퉁이에
    점이 찍힌 것처럼 나타난다. 투명한 자리에는 색을 남기지 않는 것이 안전하다.
    """
    cleaned = image.convert("RGBA")
    pixels = cleaned.load()
    width, height = cleaned.size
    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            if a < 16:
                pixels[x, y] = (0, 0, 0, 0)
    return cleaned


def generate() -> pathlib.Path:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    canvas = _rounded_gradient_background(CANVAS)
    _draw_archive_glyph(canvas)

    png_path = ASSETS_DIR / "icon_256.png"
    canvas.resize((256, 256), Image.LANCZOS).save(png_path)

    ico_path = ASSETS_DIR / "icon.ico"
    ico_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    # 크기별로 직접 줄이고 모서리를 정리한 뒤 넣는다. Pillow에 축소를 맡기면
    # 작은 크기에서 모서리에 반투명 색 픽셀이 남는다.
    #
    # 기준 이미지는 반드시 원본 캔버스여야 한다. Pillow는 기준 이미지보다 큰 크기를
    # 목록에서 버리므로, 16x16을 기준으로 주면 16x16짜리 아이콘 하나만 저장된다.
    frames = [_clean_alpha(canvas.resize(size, Image.LANCZOS)) for size in ico_sizes]
    _clean_alpha(canvas).save(
        ico_path, format="ICO", sizes=ico_sizes, append_images=frames
    )

    icns_path = ASSETS_DIR / "icon.icns"
    icns_sizes = [(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512), (1024, 1024)]
    canvas.save(icns_path, format="ICNS", sizes=icns_sizes)

    return ico_path


if __name__ == "__main__":
    out = generate()
    print(f"아이콘 생성 완료: {out}")
