"""Скриншоты/видео: скролл именно section[data-testid=stMain] у Streamlit."""

from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

BASE = os.environ.get("DEMO_BASE_URL", "https://salesanalytics.alexklyvibe.ru").rstrip("/")
USER = os.environ.get("BASIC_AUTH_USER", "admin")
PASSWORD = os.environ.get("BASIC_AUTH_PASSWORD", "")
if not PASSWORD:
    raise SystemExit(
        "Задайте BASIC_AUTH_PASSWORD в окружении (не храните пароль в репозитории)."
    )

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "docs" / "screenshots"
VIDEO_DIR = ROOT / "docs" / "demo"
RAW_VIDEO = VIDEO_DIR / "_raw"
SHOTS.mkdir(parents=True, exist_ok=True)
VIDEO_DIR.mkdir(parents=True, exist_ok=True)
RAW_VIDEO.mkdir(parents=True, exist_ok=True)

VIEW_W = 1440
VIEW_H = 900
HOLD = 1.25
STEP = 420


def log(msg: str) -> None:
    print(msg, flush=True)


def sleep(sec: float) -> None:
    time.sleep(sec)


def wait_spinners_gone(page: Page, timeout_s: float = 45.0) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if page.locator('[data-testid="stSpinner"]').count() == 0:
                sleep(0.5)
                return
        except Exception:
            return
        sleep(0.3)


def wait_ready(page: Page, extra: float = 2.0) -> None:
    try:
        page.wait_for_load_state("domcontentloaded", timeout=20000)
    except Exception:
        pass
    sleep(extra)
    wait_spinners_gone(page)


def main_metrics(page: Page) -> dict:
    return page.evaluate(
        """() => {
          const main = document.querySelector('[data-testid="stMain"]')
            || document.querySelector('section.stMain')
            || document.querySelector('section.main');
          if (!main) {
            return {ok:false, sh: window.innerHeight, ch: window.innerHeight, top: 0};
          }
          return {
            ok: true,
            sh: main.scrollHeight,
            ch: main.clientHeight,
            top: main.scrollTop,
          };
        }"""
    )


def scroll_main(page: Page, y: int) -> None:
    page.evaluate(
        """(y) => {
          const main = document.querySelector('[data-testid="stMain"]')
            || document.querySelector('section.stMain')
            || document.querySelector('section.main');
          if (main) main.scrollTop = y;
        }""",
        max(0, int(y)),
    )


def scroll_tour_video(page: Page) -> None:
    scroll_main(page, 0)
    sleep(HOLD)
    m = main_metrics(page)
    max_top = max(m["sh"] - m["ch"], 0)
    y = 0
    while y < max_top:
        y = min(y + STEP, max_top)
        scroll_main(page, y)
        sleep(0.55)
        # высота может вырасти после догрузки графиков
        m = main_metrics(page)
        max_top = max(m["sh"] - m["ch"], 0)
    scroll_main(page, max_top)
    sleep(HOLD)
    scroll_main(page, 0)
    sleep(0.35)


def shot_scrolled(page: Page, name: str) -> None:
    scroll_main(page, 0)
    sleep(0.4)
    # прогрев
    m = main_metrics(page)
    max_top = max(m["sh"] - m["ch"], 0)
    y = 0
    while y < max_top:
        y = min(y + 700, max_top)
        scroll_main(page, y)
        sleep(0.3)
        m = main_metrics(page)
        max_top = max(m["sh"] - m["ch"], 0)
    scroll_main(page, 0)
    sleep(0.5)
    m = main_metrics(page)
    max_top = max(m["sh"] - m["ch"], 0)
    log(f"height {name}: sh={m['sh']} ch={m['ch']} max_top={max_top}")

    # части экрана
    y = 0
    idx = 1
    while True:
        scroll_main(page, y)
        sleep(0.4)
        path = SHOTS / f"{name}_{idx:02d}.png"
        page.screenshot(path=str(path), full_page=False)
        log(f"shot {path.name} y={y}/{max_top}")
        if y >= max_top:
            break
        y = min(y + int(VIEW_H * 0.88), max_top)
        idx += 1
        if idx > 30:
            break

    # один tall screenshot через временный viewport ≈ scrollHeight
    scroll_main(page, 0)
    sleep(0.3)
    tall = min(max(int(m["sh"]) + 40, VIEW_H), 12000)
    # Streamlit: увеличиваем высоту stMain через viewport, чтобы убрать внутренний скролл
    page.set_viewport_size({"width": VIEW_W, "height": tall})
    sleep(1.0)
    # после resize высота может пересчитаться — скролл в 0
    scroll_main(page, 0)
    sleep(0.5)
    full = SHOTS / f"{name}_full.png"
    page.screenshot(path=str(full), full_page=True)
    log(f"shot_full {full.name} viewport_h={tall}")
    page.set_viewport_size({"width": VIEW_W, "height": VIEW_H})
    sleep(0.5)
    scroll_main(page, 0)


def click_nav(page: Page, title: str) -> None:
    log(f"nav -> {title}")
    selectors = [
        f'[data-testid="stSidebarNav"] a:has-text("{title}")',
        f'[data-testid="stSidebar"] a:has-text("{title}")',
    ]
    for sel in selectors:
        loc = page.locator(sel)
        try:
            if loc.count() and loc.first.is_visible(timeout=2000):
                loc.first.click(timeout=8000)
                wait_ready(page, extra=2.3)
                return
        except Exception:
            continue
    page.get_by_text(title, exact=True).first.click(timeout=8000)
    wait_ready(page, extra=2.3)


def click_button(page: Page, label: str) -> bool:
    log(f"click ~ {label}")
    btn = page.get_by_role("button", name=re.compile(label, re.I))
    try:
        if btn.count() and btn.first.is_visible(timeout=2500):
            btn.first.click(timeout=8000)
            return True
    except Exception:
        return False
    return False


def demo_page(
    page: Page,
    *,
    name: str,
    nav: str | None = None,
    action: str | None = None,
    action_wait: float = 8.0,
) -> None:
    if nav:
        click_nav(page, nav)
    else:
        wait_ready(page, extra=1.2)
    if action and click_button(page, action):
        wait_ready(page, extra=action_wait)
        wait_spinners_gone(page, timeout_s=70)
        sleep(1.0)
    log(f"video-scroll {name}")
    scroll_tour_video(page)
    log(f"screenshots {name}")
    shot_scrolled(page, name)
    sleep(HOLD)


def main() -> None:
    for old in SHOTS.glob("*.png"):
        old.unlink()
    for old in RAW_VIDEO.glob("*"):
        try:
            old.unlink()
        except OSError:
            pass

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": VIEW_W, "height": VIEW_H},
            http_credentials={"username": USER, "password": PASSWORD},
            ignore_https_errors=True,
            record_video_dir=str(RAW_VIDEO),
            record_video_size={"width": VIEW_W, "height": VIEW_H},
            locale="ru-RU",
        )
        page = context.new_page()
        page.set_default_timeout(45000)

        log("open home")
        page.goto(BASE + "/", wait_until="domcontentloaded", timeout=60000)
        wait_ready(page, extra=3.0)

        demo_page(page, name="01_obzor")

        click_nav(page, "Загрузка")
        if page.get_by_text("Синтетический пример").count():
            page.get_by_text("Синтетический пример").first.click()
            wait_ready(page, extra=2.5)
        demo_page(page, name="02_zagruzka")

        demo_page(page, name="03_analitika", nav="Аналитика")
        demo_page(
            page,
            name="04_prognoz",
            nav="Прогноз",
            action="Рассчитать прогноз",
            action_wait=12.0,
        )
        demo_page(
            page,
            name="05_scenarii",
            nav="Сценарии",
            action="Рассчитать сценарии",
            action_wait=11.0,
        )
        demo_page(
            page,
            name="06_rekomendacii",
            nav="Рекомендации",
            action="Сформировать рекомендации",
            action_wait=16.0,
        )
        demo_page(page, name="07_obzor_final", nav="Обзор")

        video_path = page.video.path() if page.video else None
        context.close()
        browser.close()

        if video_path:
            webm = VIDEO_DIR / "demo_osnovnoj_scenarij.webm"
            if webm.exists():
                webm.unlink()
            Path(video_path).replace(webm)
            log(f"video_webm {webm}")
            try:
                import imageio_ffmpeg

                ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
                mp4 = VIDEO_DIR / "demo_osnovnoj_scenarij.mp4"
                subprocess.run(
                    [
                        ffmpeg,
                        "-y",
                        "-i",
                        str(webm),
                        "-c:v",
                        "libx264",
                        "-pix_fmt",
                        "yuv420p",
                        "-movflags",
                        "+faststart",
                        str(mp4),
                    ],
                    check=True,
                    capture_output=True,
                )
                log(f"video_mp4 {mp4} size={mp4.stat().st_size}")
            except Exception as exc:  # noqa: BLE001
                log(f"mp4_fail {exc}")

        log(f"done shots={len(list(SHOTS.glob('*.png')))}")


if __name__ == "__main__":
    main()
