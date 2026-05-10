#!/usr/bin/env python3
from __future__ import annotations
import sys
import os
import argparse
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

try:
    from rich.console import Console
    from rich.text import Text
except ImportError:
    print("Hata: 'rich' kütüphanesi gerekli.  -->  pip install rich", file=sys.stderr)
    sys.exit(1)

# Windows'ta UnicodeEncodeError (cp1254) hatasını önlemek için UTF-8 zorla
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

console = Console()

BAR_CHAR      = "█"
MAX_BAR_WIDTH = 28
TOP_N         = 3
NOW           = datetime.now()

# Tazelik eşikleri
_24H = timedelta(hours=24)
_30D = timedelta(days=30)
_1Y  = timedelta(days=365)


# ── Tazelik yardımcıları ────────────────────────────────────────────────────

def freshness_style(mtime: float | None) -> str:
    """mtime'a göre rich renk stili döndürür."""
    if mtime is None:
        return "dim white"
    age = NOW - datetime.fromtimestamp(mtime)
    if age <= _24H:
        return "bold bright_green"   # son 24 saat
    if age <= _30D:
        return "yellow"              # son 1 ay
    if age <= _1Y:
        return "bright_black"        # 1 aydan eski, 1 yıldan genç → koyu gri
    return "bold red"                # 1 yıldan eski → silme adayı


def age_label(mtime: float | None) -> str:
    """İnsan okunabilir yaş etiketi (ör: '3s önce', '12g önce')."""
    if mtime is None:
        return "?"
    secs = int((NOW - datetime.fromtimestamp(mtime)).total_seconds())
    if secs < 3600:
        return f"{secs // 60}dk önce"
    if secs < 86400:
        return f"{secs // 3600}s önce"
    days = secs // 86400
    if days < 30:
        return f"{days}g önce"
    if days < 365:
        return f"{days // 30}ay önce"
    return f"{days // 365}y önce"


# ── Ağaç ve İstatistik Toplama (Single Pass & os.scandir) ─────────────────────

def _analyze_dir(path_str: str, recursive: bool, scan_subdirs: bool = True) -> tuple[int, float | None, Counter, list]:
    """
    Belirtilen dizini tek seferde tarar (single pass).
    Döndürdüğü değerler:
      - file_count: Toplam dosya sayısı (recursive ise alt dizinler dahil)
      - max_mtime: En yeni dosyanın değiştirilme tarihi
      - ext_counter: Uzantıların Counter nesnesi
      - child_nodes: [(Path, count, mtime, exts, children), ...]
    """
    file_count = 0
    max_mtime = None
    ext_counter = Counter()
    child_nodes = []

    try:
        subdirs = []
        with os.scandir(path_str) as it:
            for entry in it:
                if entry.is_dir(follow_symlinks=False):
                    # Tüm DirEntry nesnesini RAM'de tutmak yerine sadece ismini alıyoruz.
                    subdirs.append(entry.name)
                elif entry.is_file(follow_symlinks=False):
                    file_count += 1
                    try:
                        stat = entry.stat(follow_symlinks=False)
                        if max_mtime is None or stat.st_mtime > max_mtime:
                            max_mtime = stat.st_mtime
                    except OSError:
                        pass
                    
                    _, ext = os.path.splitext(entry.name)
                    ext = ext.lower() if ext else "(yok)"
                    ext_counter[ext] += 1
            
        # Alt klasörleri alfabetik sıralıyoruz.
        # with bloğundan çıkarak os.scandir() file descriptor'ını hızlıca serbest bıraktık!
        subdirs.sort()

        for subdir_name in subdirs:
            if not scan_subdirs:
                continue
            
            subdir_path = os.path.join(path_str, subdir_name)
            
            if recursive:
                sub_cnt, sub_mtime, sub_exts, sub_children = _analyze_dir(subdir_path, recursive=True, scan_subdirs=True)
                
                if sub_cnt >= 0:
                    file_count += sub_cnt
                    ext_counter.update(sub_exts)
                
                if sub_mtime is not None:
                    if max_mtime is None or sub_mtime > max_mtime:
                        max_mtime = sub_mtime
                        
                top_ext_list = []
                if sub_cnt > 0:
                    top_ext_list = [(ext, round(c / sub_cnt * 100, 1)) for ext, c in sub_exts.most_common(TOP_N)]
                    
                child_nodes.append((Path(subdir_path), sub_cnt, sub_mtime, top_ext_list, sub_children))
            else:
                # Recursive değilse, sadece bu alt klasörün hemen içindeki dosyaları sayarız
                sub_cnt, sub_mtime, sub_exts, _ = _analyze_dir(subdir_path, recursive=False, scan_subdirs=False)
                
                top_ext_list = []
                if sub_cnt > 0:
                    top_ext_list = [(ext, round(c / sub_cnt * 100, 1)) for ext, c in sub_exts.most_common(TOP_N)]
                    
                child_nodes.append((Path(subdir_path), sub_cnt, sub_mtime, top_ext_list, []))

    except (PermissionError, OSError):
        return -1, None, Counter(), []

    return file_count, max_mtime, ext_counter, child_nodes


def collect_tree(path: Path, recursive: bool) -> list:
    """Ağacı oluşturur ve kök dizinin altındaki node listesini döndürür."""
    _, _, _, child_nodes = _analyze_dir(str(path), recursive=recursive, scan_subdirs=True)
    return child_nodes


def find_max(nodes: list) -> int:
    m = 0
    for _, count, _mt, _ex, children in nodes:
        if count > m:
            m = count
        cm = find_max(children)
        if cm > m:
            m = cm
    return m


# ── Çizim ────────────────────────────────────────────────────────────────────

def render_tree(nodes: list, max_count: int, prefix: str = "") -> None:
    for i, (path, count, mtime, exts, children) in enumerate(nodes):
        is_last      = (i == len(nodes) - 1)
        connector    = "└── " if is_last else "├── "
        child_prefix = prefix + ("    " if is_last else "│   ")
        style        = freshness_style(mtime)
        age          = age_label(mtime)

        line = Text()
        line.append(f"{prefix}{connector}", style="dim white")
        line.append(f"{path.name}/", style="bold yellow")
        line.append("  ")

        if count < 0:
            line.append("(erişim reddedildi)", style="dim red")
        else:
            bar_len = int(count / max_count * MAX_BAR_WIDTH) if max_count > 0 else 0
            line.append(BAR_CHAR * bar_len, style=style)
            line.append(" " * (MAX_BAR_WIDTH - bar_len))
            line.append(f"  {count:>5} dosya", style="green")
            line.append(f"  {age:<10}", style=style)

            # Uzantı tablosu
            line.append("║ ", style="dim white")
            for j, (ext, pct) in enumerate(exts):
                if j > 0:
                    line.append(" │ ", style="dim white")
                line.append(f"{ext:<7}", style="magenta")
                line.append(f"{pct:>5.1f}%", style="white")
            for _ in range(TOP_N - len(exts)):
                line.append(" │ " + " " * 13, style="dim white")

        console.print(line)
        if children:
            render_tree(children, max_count, child_prefix)


def print_legend() -> None:
    console.print()
    t = Text("  Tazelik: ")
    t.append("██ Son 24 saat", style="bold bright_green")
    t.append("   ")
    t.append("██ Son 1 ay", style="yellow")
    t.append("   ")
    t.append("██ 1 aydan eski", style="bright_black")
    t.append("   ")
    t.append("██ 1 yıldan eski (silme adayı)", style="bold red")
    console.print(t)
    console.print()


def print_header() -> None:
    cols  = f"{'Dizin / Çubuk (tazeliğe göre renkli)':<52}{'Dosya':>7}  {'Yaş':<10}  "
    cols += "║  " + "  │  ".join(f"#{i} Uzantı     " for i in range(1, TOP_N + 1))
    console.print(f"  [bold white]{cols}[/bold white]")
    console.print(f"  [dim]{'─' * (len(cols) + 4)}[/dim]")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dizin ağacını dosya sayısı, tazelik rengi ve uzantı analizi ile gösterir."
    )
    parser.add_argument("directory", nargs="?", default=".", help="Taranacak dizin (varsayılan: .)")
    parser.add_argument("-r", "--recursive", action="store_true",
                        help="Alt dizinleri özyinelemeli tara")
    args = parser.parse_args()

    root = Path(args.directory).expanduser().resolve()
    if not root.exists():
        console.print(f"[red]Hata:[/red] '{root}' bulunamadı.")
        sys.exit(1)
    if not root.is_dir():
        console.print(f"[red]Hata:[/red] '{root}' bir dizin değil.")
        sys.exit(1)

    mode = "özyinelemeli" if args.recursive else "yalnızca doğrudan alt dizinler"
    console.print(f"\n  [bold white]{root}[/bold white]  [dim][{mode}][/dim]")
    print_legend()
    print_header()

    nodes = collect_tree(root, args.recursive)
    if not nodes:
        console.print("  (alt dizin bulunamadı)")
        console.print()
        return

    max_count = find_max(nodes) or 1
    render_tree(nodes, max_count)
    console.print()


if __name__ == "__main__":
    main()
