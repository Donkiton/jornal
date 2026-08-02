from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
VISUALS = ROOT / "visuals"
FONT_REGULAR = Path(r"C:\Windows\Fonts\segoeui.ttf")
FONT_BOLD = Path(r"C:\Windows\Fonts\segoeuib.ttf")

INK = "#17233B"
MUTED = "#53617A"
BLUE = "#1769E0"
PALE_BLUE = "#EAF2FF"
WHITE = "#FFFFFF"


def font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_BOLD if bold else FONT_REGULAR), size)


def rounded_panel(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill: tuple[int, int, int, int]) -> None:
    draw.rounded_rectangle(box, radius=28, fill=fill)


def brand(draw: ImageDraw.ImageDraw, x: int, y: int, size: int) -> None:
    draw.ellipse((x, y + 4, x + size, y + 4 + size), fill=BLUE)
    draw.text((x + size + 15, y), "ЖУРНАЛ ПАЦИЕНТОВ", font=font(size + 3, bold=True), fill=INK)


def button(draw: ImageDraw.ImageDraw, x: int, y: int, label: str, text_size: int) -> None:
    button_font = font(text_size, bold=True)
    bounds = draw.textbbox((0, 0), label, font=button_font)
    width = bounds[2] - bounds[0] + 60
    height = bounds[3] - bounds[1] + 34
    draw.rounded_rectangle((x, y, x + width, y + height), radius=18, fill=BLUE)
    draw.text((x + 30, y + 14), label, font=button_font, fill=WHITE)


def render_hero() -> None:
    image = Image.open(VISUALS / "01-hero-background.png").convert("RGBA")
    draw = ImageDraw.Draw(image, "RGBA")
    w, h = image.size
    x = int(w * 0.055)
    brand(draw, x, int(h * 0.115), 18)
    draw.text((x, int(h * 0.225)), "Учёт операций\nи анестезии —\nв одном окне", font=font(int(h * 0.061), bold=True), fill=INK, spacing=3)
    draw.text((x, int(h * 0.545)), "Быстрый ввод, поиск и справочники\nбез лишней бумажной рутины.", font=font(int(h * 0.024)), fill=MUTED, spacing=8)
    button(draw, x, int(h * 0.685), "Запросить демонстрацию", int(h * 0.021))
    image.convert("RGB").save(VISUALS / "01-hero.png", quality=95)


def render_features() -> None:
    image = Image.open(VISUALS / "02-features-background.png").convert("RGBA")
    draw = ImageDraw.Draw(image, "RGBA")
    w, h = image.size
    x = int(w * 0.075)
    brand(draw, x, int(h * 0.05), 16)
    draw.text((x, int(h * 0.115)), "Меньше ручной\nрутины", font=font(int(h * 0.056), bold=True), fill=INK, spacing=2)
    draw.text((x, int(h * 0.25)), "Быстрый ввод  •  Поиск  •  Авторасчёт времени", font=font(int(h * 0.019)), fill=MUTED)
    image.convert("RGB").save(VISUALS / "02-features.png", quality=95)


def render_data_control() -> None:
    image = Image.open(VISUALS / "03-data-control-background.png").convert("RGBA")
    draw = ImageDraw.Draw(image, "RGBA")
    w, h = image.size
    x = int(w * 0.075)
    brand(draw, x, int(h * 0.05), 16)
    draw.text((x, int(h * 0.115)), "Контроль места\nхранения данных", font=font(int(h * 0.052), bold=True), fill=INK, spacing=2)
    draw.text((x, int(h * 0.245)), "Путь к базе выбирается в настройках.\nРезервная копия — раз в неделю.", font=font(int(h * 0.019)), fill=MUTED, spacing=6)
    image.convert("RGB").save(VISUALS / "03-data-control.png", quality=95)


def render_workflow() -> None:
    image = Image.open(VISUALS / "04-workflow-background.png").convert("RGBA")
    draw = ImageDraw.Draw(image, "RGBA")
    w, h = image.size
    x = int(w * 0.045)
    panel = (x, int(h * 0.045), int(w * 0.57), int(h * 0.34))
    rounded_panel(draw, panel, (255, 255, 255, 226))
    brand(draw, x + 28, int(h * 0.072), 14)
    draw.text((x + 28, int(h * 0.13)), "Ввод и поиск\nбез лишних окон", font=font(int(h * 0.047), bold=True), fill=INK, spacing=2)
    draw.text((x + 28, int(h * 0.255)), "Журнал, фильтры и быстрая форма — рядом.", font=font(int(h * 0.017)), fill=MUTED)
    image.convert("RGB").save(VISUALS / "04-workflow.png", quality=95)


def render_pilot() -> None:
    image = Image.open(VISUALS / "05-pilot-background.png").convert("RGBA")
    draw = ImageDraw.Draw(image, "RGBA")
    w, h = image.size
    x = int(w * 0.055)
    brand(draw, x, int(h * 0.13), 18)
    draw.text((x, int(h * 0.245)), "Пилот для одного\nотделения", font=font(int(h * 0.065), bold=True), fill=INK, spacing=2)
    draw.text((x, int(h * 0.47)), "Проверьте сценарии на реальной работе\nдо масштабного внедрения.", font=font(int(h * 0.023)), fill=MUTED, spacing=7)
    button(draw, x, int(h * 0.63), "Запросить демонстрацию", int(h * 0.021))
    image.convert("RGB").save(VISUALS / "05-pilot.png", quality=95)


if __name__ == "__main__":
    render_hero()
    render_features()
    render_data_control()
    render_workflow()
    render_pilot()
